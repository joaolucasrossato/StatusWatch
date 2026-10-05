# HTTP Monitoring Engine — v0.4.0

> Documento da etapa histórica indicada no título. Para o estado consolidado,
> consulte o [README](../README.md), a [retenção](retention.md),
> a [segurança](security.md) e a [validação v1.0](validation-v1.0.md).

## Arquitetura

```text
Usuário → React → FastAPI → PostgreSQL
                             ↑    ↑
                       scheduler  MonitorCheck
                             ↓    ↑
                        HTTP checker → destino público

Redis: probe de inicialização; sem fila/locks nesta versão.
```

API mantém JWT/Argon2, ownership e CRUD. O scheduler roda exclusivamente no serviço `worker`, nunca no lifespan da API. SQLAlchemy permanece síncrono: consultas e persistência são executadas com `asyncio.to_thread`, cada operação com sua própria Session. Nenhuma Session/conexão de banco permanece aberta durante HTTP.

## Ciclo e persistência

1. Worker valida PostgreSQL e Redis usando os probes existentes.
2. Cria um AsyncClient reutilizado durante todo seu ciclo de vida.
3. Busca monitores ativos com `MAX(checked_at)` agrupado por monitor em uma consulta, sem carregar o histórico.
4. Sem check: due imediato. Caso contrário: `now >= checked_at + interval_seconds`.
5. Consumidores assíncronos em quantidade fixa processam os monitores due.
6. Revalida estado/configuração antes de iniciar a rede. Executa GET com segurança e retorna `CheckResult` tipado.
7. Abre transação curta, bloqueia a linha do monitor, revalida estado/configuração e insere `MonitorCheck`. Se pausado, removido ou alterado, descarta o resultado em voo.
8. Espera o intervalo de polling e repete. Falhas de consulta/persistência são registradas sem dados sensíveis; a Session faz rollback/close e o próximo ciclo continua.

Os intervalos existentes são 30, 60, 300 ou 600 segundos; timeout 1–30 segundos. `checked_at` registra conclusão, em UTC. Reinícios usam os checks persistidos, sem depender de memória. Pausados não geram novos registros; checks antigos permanecem. Um request já em voo quando ocorre a pausa pode terminar, mas seu resultado não será persistido enquanto pausado. A atualização no banco serializa com a persistência por lock de linha.

O scheduler espera o lote atual terminar antes do próximo ciclo. O intervalo é mínimo entre a conclusão anterior e uma próxima tentativa, não uma garantia de execução em horário exato. Polling, carga e duração do lote podem atrasar a execução. Não há retries imediatos de HTTP. Falha de persistência deixa o monitor due para o próximo ciclo.

SIGINT/SIGTERM cancelam o scheduler e os requests em voo, fecham o cliente e as dependências. Tentativas canceladas podem não gerar check. Operações de banco já iniciadas em threads terminam sob os timeouts existentes (conexão/pool/query: 3 segundos). Não há health server próprio; logs mostram inicialização, conclusão por monitor e shutdown. Redis não é utilizado como queue.

## Configuração

| Variável | Default | Limites |
| --- | --- | --- |
| WORKER_MAX_CONCURRENCY | 10 | 1–100 |
| WORKER_POLL_INTERVAL_SECONDS | 5 | 0.1–60 |
| WORKER_MAX_REDIRECTS | 5 | 0–10 |

Presentes no `.env.example` e nos Compose raiz de desenvolvimento/produção. Os arquivos `backend/compose*.yaml` antigos são fragmentos sem serviços, não são entrypoints da stack.

## Dados e migration

`Monitor.checks ↔ MonitorCheck.monitor` usa `back_populates`, cascade ORM e FK `ON DELETE CASCADE`. UUIDs são gerados pela aplicação. `status` é string validada por constraint UP/DOWN; Pending não é um registro. HTTP code, duração, error_type e error_message são nullable. Mensagem tem limite de 200 caracteres e usa somente um catálogo fixo, nunca texto de exceção. `checked_at` é timestamp timezone-aware com default `now()` no servidor; worker fornece UTC na conclusão.

O índice composto `(monitor_id, checked_at)` indexa o FK pela primeira coluna, acelera seleção do último check e dispensa índice simples redundante. A ordenação usa `checked_at DESC, id DESC` para desempate determinístico. Duração tem constraint não negativa. Não há retenção automática.

Revision `b7c4e920d631`, down_revision `9d2f3a7c8b10`. Upgrade cria somente monitor_checks/índice/constraints; downgrade remove somente esses recursos. Migrations anteriores não foram alteradas.

## HTTP e tempo

GET assíncrono com httpx 0.28.1 / httpcore 1.0.9, TLS verificado. HTTP 200–399 é UP, 400–599 é DOWN; demais códigos finais são DOWN. 301/302/303/307/308 com Location são seguidos manualmente; cada destino é validado. Redirect sem Location e outros 3xx são classificados como UP. Limite excedido é DOWN/redirect_limit, mesmo que o último status intermediário tenha sido 3xx.

Um deadline total `asyncio.timeout(timeout_seconds)` cobre DNS, TCP/TLS, headers e todos os redirects. Há também timeout httpx por operação. `response_time_ms` mede monotonicamente desde o início da tentativa até os headers finais ou a falha, incluindo validação DNS e redirects, sem ler o corpo. Portanto não representa download completo nem TTFB isolado. Falhas e bloqueios também recebem a duração da tentativa.

| error_type | Significado |
| --- | --- |
| timeout | Deadline total ou timeout HTTP |
| dns_error | Falha de resolução/nenhum endereço |
| connection_refused | Conexão recusada identificável na cadeia da exceção |
| connection_error | Falha de conexão sem causa mais específica |
| tls_error | Falha TLS/certificado identificável |
| network_error | Protocolo HTTP ou outra falha de rede |
| invalid_destination | URL inválida, esquema não permitido, userinfo ou zona IPv6 |
| ssrf_blocked | Destino não público |
| redirect_limit | Mais redirects que o configurado |
| unexpected_error | Fallback sanitizado; classe da exceção registrada no log |

Erros retornam DOWN com HTTP code null. Respostas 4xx/5xx mantêm o código, sem inventar um erro de transporte. Bloqueios SSRF são tentativas legítimas do scheduler: geram DOWN/ssrf_blocked sem request ao destino bloqueado. Nenhum body, query string, URL, JWT ou texto bruto de exceção entra nos logs do worker. Logs HTTPX/HTTPCore ficam em WARNING; eventos do engine usam somente UUID e campos controlados.

## SSRF: política e limites

Um serviço que faz requests a URLs de usuários pode ser usado para atingir infraestrutura interna. Por isso validar somente HTTP/HTTPS ou a palavra localhost é insuficiente.

- Parser HTTPX e Pydantic; somente HTTP/HTTPS, GET. Userinfo é rejeitado em criação/edição e no checker para registros antigos/redirects. Fragmentos não são enviados. Portas explícitas são preservadas.
- DNS A/AAAA via resolver do sistema, fora do event loop. **Todos** os endereços precisam ser públicos; resposta mista pública/privada é bloqueada inteira. Nomes numéricos alternativos passam pelo resolver e pela mesma validação.
- `ipaddress` bloqueia loopback, private, link-local, multicast, unspecified, reserved e endereços não globais, tanto IPv4 quanto IPv6 (inclui shared CGNAT e documentação). Localhost explícito, IPv4 mapped, 6to4, Teredo, NAT64 conhecido e zonas IPv6 são recusados conservadoramente.
- A conexão usa o primeiro IP validado na URL efetiva; o nome original é preservado em Host e na extensão `sni_hostname` para verificação TLS. Não ocorre uma segunda resolução do nome original no transporte. Testes exercitam HTTPX/HTTPCore até a fronteira de socket e verificam IP, SNI, Host e SSL CERT_REQUIRED/check_hostname.
- O AsyncClient é reutilizado, mas keepalive é desabilitado: conexões indexadas por IP não podem ser reutilizadas entre nomes virtuais diferentes. Cookies são removidos antes de cada request. Proxies/configurações de ambiente são ignorados (`trust_env=False`), evitando outro caminho de resolução/conexão.
- Redirects relativos são resolvidos contra a URL original daquele hop; absolutos e relativos passam novamente por DNS/política/pinagem. Redirect para IP privado nunca faz request ao IP privado.

A pinagem fecha a janela usual de DNS rebinding entre resolução validada e conexão. **Não é garantia absoluta de isolamento de rede**: roteamento/NAT customizado, proxies públicos, alterações futuras da biblioteca, destinos públicos que expõem serviços sensíveis e ranges novos exigem controles adicionais. Prefixos NAT64 customizados não são enumeráveis pela aplicação. Recomenda-se egress firewall independente, política de destinos/portas adequada ao ambiente e revisão dos testes ao atualizar HTTPX/HTTPCore/Python. Nesta versão escolhe-se apenas o primeiro IP válido, sem fallback Happy Eyeballs: uma falha nesse endereço pode gerar DOWN mesmo havendo outro IP acessível.

O cancelamento limita a espera assíncrona por DNS, mas o resolver nativo em thread pode continuar até seu timeout do sistema; resolução excessivamente lenta pode atrasar encerramento completo do executor. Docker aplica seu limite de parada de 15 segundos. Proteção adicional de DNS/egress fica para operação futura.

## API e frontend

`GET /monitors/{monitor_id}/checks/latest` exige JWT e ownership existentes. Monitor alheio/inexistente → 404; token ausente/inválido → 401; UUID inválido → 422. Sem check → **200 com JSON null**. Com check → 200 com status, http_status_code, response_time_ms, error_type, error_message e checked_at. Cache-Control: no-store.

GET /monitors também inclui `latest_check` (objeto ou null), obtido em consulta única com subconsulta correlacionada e índice. GET individual/PATCH incluem o mesmo campo. Não há endpoint de histórico.

Interface distingue Monitoring Active/Paused de Operational status UP/DOWN/Pending. Mostra código HTTP, duração, mensagem sanitizada e data local; pausados mantêm o último resultado com aviso explícito. Lista atualiza a cada 30 segundos enquanto visível, sem polling durante edição/confirmação/mutação, com cleanup do timer ao desmontar. Falha de refresh é exibida sem inventar Pending/UP. Autenticação continua em memória.

## Docker e validação manual

Preservados os cinco serviços db/redis/api/worker/web, imagens dev/prod e gateway Nginx. API/db/Redis continuam privados em produção. Rede bridge permite saída à internet; não foi marcada internal.

```bash
docker compose config --quiet
docker compose build api worker web
docker compose up -d db redis
docker compose run --rm api alembic upgrade head
docker compose up -d --wait
docker compose logs --tail 20 worker
```

Teste manual seguro: entre pela UI, crie **um** monitor para uma URL pública de teste que você controla (intervalo 60 segundos, timeout 10); aguarde um ciclo; consulte o endpoint latest com seu JWT ou observe o refresh da UI. Confirme código, duração e data. Pause o monitor, aguarde mais que um intervalo e confirme que a data não muda; remova o monitor ao terminar. Para testar bloqueio sem tocar infraestrutura interna, use `http://127.0.0.1`: espera-se DOWN/ssrf_blocked e nenhum request ao destino. Não cole JWT em relatórios.

Suite automatizada não usa internet pública. `tests/validate_migrations.py` cria banco descartável e prova upgrade → downgrade → upgrade com users e monitors preservados. Nunca faça downgrade de validação no banco real.

## Limitações e fronteira

Uma réplica de worker. Múltiplos schedulers podem produzir checks duplicados; não existe claiming/lock distribuído. Scheduler carrega configurações ativas em memória; listagem sem paginação permanece como v0.3. Checks crescem sem limite: retenção, agregação e eventual particionamento serão necessários em escala. Falha de banco pode perder resultado; pausa seguida de reativação ou edição desfeita durante o mesmo request não possui versionamento de configuração. Não há garantias de execução exatamente uma vez.

Sem uptime, gráficos, histórico paginado, analytics, incidentes, thresholds, alertas, notificações, status pages, outros protocolos/métodos, custom headers, Celery/queues, observabilidade externa, Kubernetes ou billing. Essas funcionalidades permanecem fora da v0.4.
