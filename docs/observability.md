# Observabilidade — StatusWatch v1.1

A fase de métricas/alerting contém Prometheus, Grafana, Node Exporter, cAdvisor e
Alertmanager. A instrumentação do checkpoint `f77e2c4` permanece intacta. Use os
Compose **da raiz**; os fragmentos antigos em `backend/` continuam preservados e
não são entrypoints (conforme `docs/operations.md`). As definições compartilhadas
ficam em `observability/compose.services.yaml`, importadas com `extends`.

## Arquitetura e componentes

```text
Grafana -> Prometheus -> api:8000/metrics
                     -> worker:WORKER_METRICS_PORT/metrics
                     -> node-exporter:9100/metrics (gateway Docker do host)
                     -> cadvisor:8080/metrics
                     -> prometheus:9090/metrics
                     -> alertmanager:9093/metrics
           |
           +-- alertas --> Alertmanager --> receiver local-only (sem envio externo)
```

| Componente | Imagem fixada | Função |
| --- | --- | --- |
| Prometheus | `prom/prometheus:v3.13.4` | Scraping, TSDB, recording rules e alertas |
| Grafana | `grafana/grafana:13.2.3` | Quatro dashboards e datasource provisionados |
| Node Exporter | `prom/node-exporter:v1.12.1` | CPU, memória, load, discos e rede do host |
| cAdvisor | `ghcr.io/google/cadvisor:0.60.6` | CPU, memória, rede e I/O por container |
| Alertmanager | `prom/alertmanager:v0.34.1` | Agrupamento e estado dos alertas |

Versões explícitas verificadas nas fontes oficiais; Prometheus usa a release LTS.
Atualizações exigem repetir as validações abaixo. Tags não substituem pin por
digest nem uma auditoria contínua de vulnerabilidades.

Fontes: [Prometheus releases](https://prometheus.io/download/),
[Node Exporter em Docker](https://github.com/prometheus/node_exporter#docker),
[cAdvisor releases](https://github.com/google/cadvisor/releases/tag/v0.60.6),
[Grafana release](https://github.com/grafana/grafana/releases/tag/v13.2.3),
[provisioning Grafana](https://grafana.com/docs/grafana/latest/administration/provisioning/).

## Configuração e inicialização

Linux com Docker Engine rootful e Compose v2 com suporte a `extends` e `cgroup`.
Docker Desktop observa a VM Linux, não necessariamente o host físico. Não é uma
configuração validada para rootless, SELinux enforcing ou LXC.

Preencha `.env` (desenvolvimento) ou `.env.production` (produção):

- `GRAFANA_ADMIN_USER`: padrão `admin`.
- `GRAFANA_ADMIN_PASSWORD`: obrigatório, aleatório e independente de JWT/SMTP.
  Gere, por exemplo, com `openssl rand -hex 32` e guarde no arquivo ignorado pelo Git.
- `NODE_EXPORTER_LISTEN_ADDRESS`: gateway real da bridge Docker, obtido abaixo.
  **Não use `0.0.0.0` nem o endereço da interface externa.**
- `DOCKER_ROOT_DIR`: confirme com `docker info`, padrão `/var/lib/docker`.
- `WORKER_METRICS_PORT`: padrão 9101. O launcher do Prometheus gera sua configuração
  em `/tmp` com a mesma porta, sem alterar o YAML versionado.

```bash
docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}'
docker info --format '{{.DockerRootDir}} {{.CgroupVersion}} {{.Driver}}'
docker compose config --quiet
docker compose build
docker compose up -d --wait
```

Em uma instalação nova, aplique antes as migrations existentes seguindo o README.
Esta fase não altera schema. A senha Grafana inicializa o banco no primeiro boot;
mudar somente a variável não redefine um administrador já salvo no volume.
Use a UI/CLI oficial de recuperação para uma instalação existente.

## Portas, redes e volumes

| Serviço | Desenvolvimento | Produção |
| --- | --- | --- |
| Web | `127.0.0.1:5173` | `127.0.0.1:8080` (Nginx) |
| API | `127.0.0.1:8000` | apenas `api:8000` na rede backend |
| Worker | apenas `worker:9101` | apenas rede backend |
| Prometheus | `127.0.0.1:9090` | apenas rede Docker |
| Grafana | `127.0.0.1:3000` | apenas rede Docker |
| Alertmanager | `127.0.0.1:9093` | apenas rede Docker |
| cAdvisor | apenas `cadvisor:8080` | apenas rede Docker |
| Node Exporter | gateway Docker `:9100` | gateway Docker `:9100` |

O Node Exporter é a exceção ao DNS de service: usa `network_mode: host` e `pid: host`
para observar a rede real do host. Prometheus resolve `node-exporter` pelo
`extra_hosts` apontando para o gateway configurado. Não existe publicação Docker
`ports:` para ele; o socket HTTP está ligado somente à interface da bridge.
Outros processos/containers com acesso a essa bridge podem consultá-lo.

A rede `observability` é interna. Prometheus também participa de `statuswatch`
(dev) ou `backend` (prod) para alcançar a aplicação. Grafana e Alertmanager usam
adicionalmente `observability-access` **somente em dev**, pois uma rede Docker
exclusivamente interna não publica os bindings locais neste Engine. Essa rede
não tem serviços do produto. Produção mantém apenas a publicação existente do
Nginx; nenhum painel administrativo foi adicionado ao proxy público.

Os nomes efetivos têm prefixo do projeto: `statuswatch_observability`,
`statuswatch_observability-access`, `statuswatch_statuswatch` em dev;
`statuswatch-prod_observability`, `statuswatch-prod_backend` e
`statuswatch-prod_frontend` em prod. Não inicie dois Node Exporters no mesmo
host/endereço/porta: pare o serviço dev antes de iniciar o de produção.

Volumes novos: `prometheus_data`, `grafana_data`, `alertmanager_data`, isolados
pelo prefixo de cada projeto. Configurações são bind mounts read-only; dados
mutáveis usam named volumes. `down` preserva dados; **`down -v` apaga dados**, incluindo
banco e histórico. Não é um procedimento de troubleshooting.

Prometheus coleta e avalia a cada **30s**, com timeout de **10s**. cAdvisor faz
housekeeping a cada 30s. Retenção: **35 dias ou 2 GiB de blocos, o que limitar primeiro**.
O WAL/head pode exceder esse tamanho; não é quota rígida de disco. Os cinco dias
extras dão margem à janela SLO de 30 dias, sem prometer histórico completo caso
o limite de tamanho seja atingido. No smoke local, os cinco componentes novos
consumiram aproximadamente 358 MiB combinados; é uma amostra, não capacity planning.

## Segurança dos exporters e do proxy

Node Exporter monta `/` em `/host:ro,rslave`, sem capabilities. cAdvisor monta
rootfs, sysfs, DockerRootDir e sockets Docker/containerd em read-only, usa cgroup
namespace do host e somente `DAC_READ_SEARCH` para atravessar diretórios privados
das camadas dos containers. A ausência dessa capability causou erros de leitura
confirmados. Nenhum container usa `privileged: true`, nem `SYS_ADMIN`.

**Um socket Unix montado `:ro` não torna sua API read-only.** cAdvisor tem acesso
privilegiado às APIs locais Docker/containerd; mantenha imagem confiável, atualizada,
sem exposição pública. Isso não é isolamento contra comprometimento do exporter.
Labels de containers são limitados a projeto/service Compose; não se exportam
variáveis de ambiente, tokens ou payloads. O endpoint continua revelando metadados
operacionais (nomes/imagens/IDs), razão para mantê-lo interno.

Docker 29 com image store containerd exigiu `/run/containerd/containerd.sock`.
Em outros layouts, ajuste esse mount e o endpoint de containerd antes de subir;
não crie silenciosamente diretório onde deveria existir socket. OOM events estão
desativados: não se concede acesso a `/dev/kmsg` para esta fase.

O Nginx retorna 404 para `/metrics`, `/api/metrics` e variantes normalizadas,
preservando `/api/health` e o scrape direto em `api:8000/metrics`. Vite em dev e
a API local continuam acessíveis apenas por loopback; não publique Vite como
servidor de produção. Todos os serviços novos usam `no-new-privileges` e healthcheck
HTTP com `wget` verificado nas imagens utilizadas.

## Métricas da aplicação

API e Worker continuam com registries/processos independentes, sem multiprocess.
All names below have the `statuswatch_` prefix. Histograms also expose `_bucket`,
`_count` and `_sum` samples. Labelled series appear after the first matching event;
the metric families are exposed even before that event.

| Process | Metric | Labels / meaning |
| --- | --- | --- |
| API | `api_http_requests_total` | `method`, route template or `unmatched`, `status_code` |
| API | `api_http_request_duration_seconds` | `method`, `route`; time until response headers are available |
| API | `api_http_requests_in_progress` | `method`; active requests until response headers |
| Worker | `monitor_checks_total` | `status`: `UP`, `DOWN`; committed checks |
| Worker | `monitor_check_failures_total` | `error_type`: fixed checker error codes, `http_error` for unsuccessful HTTP status; unknown codes become `unexpected_error` |
| Worker | `monitor_check_duration_seconds` | `status`; committed check latency, milliseconds converted to seconds |
| Worker | `incident_transitions_total` | `event`: `opened`, `resolved`; committed transitions |
| Worker | `scheduler_cycles_total` | `result`: `success`, `error`; completed cycles, not individual check outcomes |
| Worker | `scheduler_cycle_duration_seconds` | Cycle execution time, including interrupted cycles, excluding poll/sleep |
| Worker | `notification_delivery_attempts_total` | `channel_type`: `EMAIL`, `WEBHOOK`; `outcome`: `success`, `error`, `cancelled` |
| Worker | `notification_deliveries_total` | `channel_type`, terminal `status`: `SENT`, `FAILED`; counted after commit |
| Worker | `notification_delivery_retries_total` | `channel_type`; committed return to `PENDING` following an error |
| Worker | `notification_delivery_duration_seconds` | `channel_type`; external attempt time, excluding claim and completion transactions |

The API does not instrument `/metrics`. Nonstandard HTTP methods use `OTHER`.
Labels contain no IDs, targets, credentials, payloads or exception messages.

Notification attempts describe the external operation, even if the subsequent
commit fails. Cancellation propagates and does not claim that a terminal state
was persisted. For SMTP, cancellation of the async waiter cannot stop an already
running synchronous send; `cancelled` describes interruption of that waiter.
Retries remain at 60 and 300 seconds, with at most three attempts.

Disabled channels and exhausted/expired claims count `FAILED` only after commit,
without creating external attempt or retry samples. Deleting a channel cascades
to its deliveries; deletion is not a terminal delivery transition. If the defensive
missing-channel branch ever encounters an orphan despite the foreign key, no
channel-labelled metric is fabricated because the channel type is unavailable.

These are process counters, not a durable audit ledger: restarts reset them, and
a process crash between commit and increment can lose an observation. Persisted
state counters are emitted in the persistence thread after successful commit so
cancellation of its async waiter does not skip the increment.


Não existe gauge de incidentes abertos sem reconciliação com o banco.

## PromQL e recording rules

Os arquivos em `observability/prometheus/` são a fonte de verdade. Counters usam
`rate`/`increase`, gauges são consultados diretamente, percentis usam buckets:

```promql
sum(rate(statuswatch_api_http_requests_total{job="api"}[5m]))
histogram_quantile(0.95, sum by (le, route) (
  rate(statuswatch_api_http_request_duration_seconds_bucket{job="api"}[5m])
))
sum by (status) (rate(statuswatch_monitor_checks_total{job="worker"}[5m]))
sum by (channel_type, outcome) (
  rate(statuswatch_notification_delivery_attempts_total{job="worker"}[5m])
)
```

Recording rules (prefixo `statuswatch:`):

| Nome | Uso |
| --- | --- |
| `api_request_rate5m` | taxa de requests elegíveis ao SLI |
| `api_error_ratio5m` | proporção 5xx elegível, dashboard e alerta |
| `api_latency_p95_5m` | p95 elegível, dashboard e alerta |
| `monitor_check_failure_ratio5m` | proporção DOWN dos alvos externos |
| `api_error_ratio30d` | erro ponderado por requests na janela observada |
| `api_availability30d` | 1 menos a proporção de erros |
| `api_error_budget_remaining30d` | fração de budget restante, pode ser negativa |
| `api_burn_rate1h` | erro de 1h dividido pelo budget de 0,1% |
| `api_latency_good_ratio30d` | fração no bucket `le="0.5"` |
| `scheduler_success_ratio30d` | fração de ciclos concluídos com success |

Ausência de série de erro equivale a zero **somente quando existe denominador**.
Divisões usam denominador protegido e filtro `total > 0`: sem tráfego, o SLI
fica sem dados. Não se converte ausência de scrape em disponibilidade perfeita.
Janelas longas usam `increase` nos counters brutos, nunca média de razões de 5m.

## Dashboards provisionados

Datasource UID `statuswatch-prometheus`, URL interna `http://prometheus:9090`.
Pasta Grafana `StatusWatch`, atualização de provisioning a cada 30s, edição pela
UI desabilitada para manter JSON como fonte de verdade.

- **StatusWatch Overview** (14 painéis): targets, API, checks, incidentes, scheduler,
  notificações, SLI, budget e burn rate.
- **StatusWatch API** (8): throughput, rotas, status, 4xx/5xx, ratio, p50/p95/p99,
  p95 por rota e requests ativos.
- **StatusWatch Monitoring Engine / Worker** (12): checks/min, categorias de falha,
  latência, ciclos, confiabilidade, transições e entregas/retries.
- **StatusWatch Infrastructure** (10): CPU/RAM/load, filesystem/rede do host,
  CPU em cores, working set, rede e I/O de disco por container.

Unidades são segundos, bytes, bytes/s, requests/s ou frações percentuais.
As 59 consultas foram executadas contra a API do Prometheus. Painéis de eventos
raros podem ficar sem dados antes do primeiro evento. Isso não é erro de query.
O driver overlayfs/containerd deste host não expõe tamanho do writable layer por
container; o painel de disco usa **I/O real** (`container_fs_reads/writes_bytes_total`),
e capacidade/ocupação são observadas no filesystem do host. Não inventa zeros.

## Alertas e Alertmanager

| Alerta | Condição inicial / sustentação | Severidade |
| --- | --- | --- |
| TargetDown | scrape de um dos seis jobs falha / 2m | critical |
| StatusWatchApiHighErrorRate | 5xx >5%, tráfego >0,1 req/s / 5m | warning |
| StatusWatchApiHighLatency | p95 >0,5s, tráfego >0,1 req/s / 10m | warning |
| StatusWatchSchedulerErrors | >=3 ciclos com erro em 5m / 2m | warning |
| StatusWatchSchedulerStalled | endpoint UP sem progresso de ciclos em 5m / 5m | critical |
| StatusWatchMonitorCheckFailureRateHigh | DOWN >90%, >=20 checks em 5m / 15m | info |
| StatusWatchNotificationFailureRateHigh | erros >20%, >=5 tentativas em 10m / 5m | warning |
| HostDiskSpaceLow | disponível <15% em filesystem gravável / 10m | warning |
| HostMemoryPressure | MemAvailable <10% / 10m | warning |

São thresholds iniciais de laboratório, para calibrar com dados reais. O alerta
de checks DOWN é informativo sobre alvos do produto; **não é um incidente automático
da infraestrutura StatusWatch**. SchedulerStalled pode demorar até cerca de dez
minutos após parar o progresso (janela + `for`). TargetDown não detecta remoção
acidental de um job da configuração; `validate.py` verifica a lista obrigatória.

Alertmanager agrupa por `alertname, job`, espera 30s, reagrupa a cada 5m e repete
a cada 4h. O receiver `local-only` é válido e mantém alertas na API/UI, mas não
envia email/webhook. A pipeline foi testada com a regra TargetDown verdadeira em
Prometheus temporário, sem alterar targets reais. O teste resolve seu alerta e
remove o container no `finally`.

Para integrar depois, adicione `email_configs` (SMTP/TLS/remetente/destinatário)
ou `webhook_configs` (URL e autenticação) a um receiver e altere `route.receiver`.
Use arquivos de secrets montados e opções `*_file` suportadas; Alertmanager não
expande automaticamente variáveis de ambiente no YAML. Valide com `amtool`,
recarregue/recrie o serviço e libere a saída de rede necessária: em produção sua
rede atual é interna. Não reutilize JWT/SMTP da aplicação e não envie alertas
para um endpoint monitorado pelo próprio StatusWatch. A versão entregue não faz
nenhuma comunicação externa de alerting.

## SLIs, SLOs e Error Budget

Janela móvel de **30 dias**, objetivos iniciais de portfólio, não SLA contratual:

| SLI | SLO | Budget | PromQL de consulta |
| --- | --- | --- | --- |
| API: requests sem 5xx / requests elegíveis | 99,9% | 0,1% dos requests | `statuswatch:api_availability30d` |
| API: requests com headers em <=500ms / requests elegíveis observados pelo histograma | 99% | 1% dos requests | `statuswatch:api_latency_good_ratio30d` |
| Engine: ciclos success / ciclos concluídos | 99,9% | 0,1% dos ciclos | `statuswatch:scheduler_success_ratio30d` |

Requests elegíveis excluem `/`, `/health`, `/docs.*`, `/redoc`, `/openapi.json` e
`unmatched`. `/metrics` já não é instrumentado. 2xx, 3xx e 4xx contam como disponíveis;
5xx contam como ruins. Não confundir rejeição legítima por autenticação/validação
com indisponibilidade. O filtro por template é idêntico nos SLIs da API.
O histograma não tem status_code, portanto o SLI de latência inclui respostas 5xx;
ele não pode medir somente requests bem-sucedidos sem nova instrumentação.

A disponibilidade de requests é calculada conceitualmente como:

```promql
1 - (
  (sum(increase(statuswatch_api_http_requests_total{job="api",route!~"/|/health|/docs.*|/redoc|/openapi.json|unmatched",status_code=~"5.."}[30d]))
   or sum(increase(statuswatch_api_http_requests_total{job="api",route!~"/|/health|/docs.*|/redoc|/openapi.json|unmatched"}[30d])) * 0)
  / clamp_min(sum(increase(statuswatch_api_http_requests_total{job="api",route!~"/|/health|/docs.*|/redoc|/openapi.json|unmatched"}[30d])), 1e-9)
)
```

A recording rule acrescenta `total > 0`, omitido acima somente para legibilidade.
O SLI de latência divide o `increase` do bucket `le="0.5"` pelo `increase` de
`_count`, com os mesmos filtros. O SLI do engine usa `1 - errors/total` em
`statuswatch_scheduler_cycles_total`, com fallback de erro zero e gate de tráfego.
As expressões executáveis completas estão em `recording_rules.yml` e possuem testes.

Justificativa: 500ms é um bucket real existente e um objetivo inicial para operações
CRUD locais; 99,9% de requests/ciclos admite falhas ocasionais sem esconder falhas
sustentadas. Não há dados de 30 dias para afirmar cumprimento desses objetivos.

Limitações essenciais:

- API totalmente fora do ar não recebe requests e não incrementa counters. Este
  SLI não mede disponibilidade percebida de ponta a ponta; use TargetDown e,
  numa evolução futura, probes externos. `up` mede scrape, não uma transação real.
- Ciclos que não terminam e falhas individuais capturadas dentro de um ciclo não
  necessariamente incrementam `result="error"`. SchedulerStalled e métricas de
  target complementam o SLI; não é garantia de pontualidade nem de persistência
  de todos os checks. Um alvo DOWN pode ser processado corretamente.
- Processos reiniciam counters; `increase` trata resets observados, mas não
  recupera eventos entre scrapes ou perdas no intervalo commit/incremento.
- TSDB nova, gaps ou retenção por tamanho produzem janela parcial. Confira
  cobertura antes de reportar um SLO mensal. Não extrapole sucesso para gaps.

Error Budget = `1 - SLO`. Para disponibilidade 99,9%, permite-se `0.001 * N`
requests ruins no conjunto de N requests elegíveis. Consumo = `bad_ratio / 0.001`;
restante = `1 - consumo`, inclusive negativo quando excedido. Um equivalente
**puramente temporal** de 0,1% em 30 dias seria **43m12s**, mas estes counters são
ponderados por eventos: esse número não é downtime medido nem permitido inferido.

Burn rate de 1h = `bad_ratio_1h / 0.001`. 1x corresponde ao ritmo do budget; 10x
consome dez vezes mais rápido. A consulta é testada, mas não há alerta multi-window
sem experiência operacional. Budgets dos outros SLOs podem ser consultados com
`(1 - statuswatch:api_latency_good_ratio30d) / 0.01` e
`(1 - statuswatch:scheduler_success_ratio30d) / 0.001` (fração consumida).

## Validação reproduzível

Na raiz, com `.env` preenchido e sem imprimir `docker compose config` com secrets:

```bash
docker compose config --quiet
docker compose --env-file .env.production -f compose.prod.yaml config --quiet
python3 -m unittest discover -s observability/tests -p 'test_config.py'
docker compose run --rm --no-deps --entrypoint /bin/promtool prometheus check config /etc/prometheus/prometheus.yml
docker compose run --rm --no-deps --entrypoint /bin/promtool prometheus check rules /etc/prometheus/alerts.yml /etc/prometheus/recording_rules.yml
docker compose run --rm --no-deps -v "$PWD/observability/tests:/tests:ro" --entrypoint /bin/promtool prometheus test rules /tests/rules.test.yml
docker compose run --rm --no-deps --entrypoint /bin/amtool alertmanager check-config /etc/alertmanager/alertmanager.yml
docker compose build
docker compose up -d --wait
# Aguarde ao menos dois scrapes (60s) antes de esperar rates.
python3 observability/validate.py
python3 observability/test_alert_pipeline.py
# Testa somente a imagem Nginx, usando a API dev; não inicia banco de produção.
docker compose --env-file .env.production -f compose.prod.yaml build web
python3 observability/tests/test_proxy.py
```

`validate.py` exige os seis targets UP, séries reais da API/Worker/host/containers,
19 rules saudáveis, datasource funcional e quatro dashboards provisionados. Também
executa cada query de painel, permitindo resultado vazio legítimo (evento ausente).
Ele lê credenciais via Compose em memória e não as imprime. Não compartilhe a saída
completa de `config`/`inspect` contendo ambientes. `test_alert_pipeline.py` recusa
receivers com integrações externas, usa um container temporário por cerca de 2–3
minutos e resolve o alerta artificial no fim. Nunca injete falhas em produção.

```bash
cd backend
source .venv/bin/activate
python -m pytest -q
python -m compileall app tests
deactivate
cd ..
git diff --check
docker compose ps
```

CI continua executando os testes existentes; o job Docker agora gera senha
Grafana efêmera para validar Compose e executa testes de boundaries, promtool e
amtool. Integração live/exporters permanece no host Linux com acesso ao daemon.

## Troubleshooting

| Sintoma | Verificação / ação |
| --- | --- |
| Target DOWN | `curl -fsS http://127.0.0.1:9090/api/v1/targets`; veja `lastError`, DNS/porta e `docker compose logs --tail 30 prometheus` |
| Grafana sem dados | `python3 observability/validate.py`; confirme datasource UID, duas amostras/60s, intervalo de tempo e eventos existentes |
| Worker 9101 inacessível | `docker compose exec worker python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:9101/metrics').status)"`; adapte à porta configurada, consulte logs e recrie Prometheus ao mudar a variável |
| API metrics inacessível | `docker compose exec prometheus wget -qO- http://api:8000/metrics`; pelo Nginx um 404 é intencional |
| Node Exporter DOWN | confira gateway de `docker network inspect bridge`, bind ocupado, mounts e `docker compose logs --tail 30 node-exporter` |
| cAdvisor responde mas sem containers | `python3 observability/validate.py`; confira factory Docker nos logs, socket containerd, cgroup v2/namespace e versão Docker; UP sozinho não basta |
| cAdvisor sem writable-layer bytes | limitação de driver/image store; confira I/O, memória e filesystem do host, não trate ausência como zero |
| Erros permission denied no filesystem | confira `DAC_READ_SEARCH` e mounts RO; não habilite privileged indiscriminadamente |
| Rules não carregadas | `docker compose exec prometheus promtool check config /tmp/prometheus.yml`; `/api/v1/rules`; valide e use `docker compose kill -s HUP prometheus` ou restart |
| Alertmanager desconectado | `curl -fsS http://127.0.0.1:9090/api/v1/alertmanagers`; `docker compose logs --tail 30 alertmanager`; confirme rede e nome `alertmanager:9093` |
| Sem email/webhook | receiver padrão é deliberadamente local-only; não há entrega externa configurada |
| UI local sem binding | confirme rede `observability-access` no dev; produção deliberadamente não publica essas portas |
| Mounts incompatíveis | confirme `DockerRootDir`, `/run/containerd/containerd.sock`, Linux rootful e cgroup; não aplique `:Z` ao filesystem inteiro do host |

Diagnóstico de scrape e regras em produção (sem publicar portas):

```bash
docker compose --env-file .env.production -f compose.prod.yaml exec prometheus wget -qO- http://127.0.0.1:9090/api/v1/targets
docker compose --env-file .env.production -f compose.prod.yaml exec prometheus wget -qO- http://127.0.0.1:9090/api/v1/rules
```

Para acessar a UI de produção, use um túnel SSH administrativo para o IP interno
do container (obtido por `docker inspect`) ou um override temporário revisado com
bind exclusivo em loopback. Não adicione Grafana/Prometheus ao proxy público sem
controle de acesso. As redes internas de produção também restringem saída para
plugins externos e notificações; planeje explicitamente qualquer integração.

## Resultado e limites desta entrega

Validação em 06/10/2026 (America/Sao_Paulo), Docker 29.8.2, cgroup v2 e overlayfs:
333 testes backend passaram, com um warning preexistente Starlette/AnyIO.
Compileall, Compose dev/prod, promtool, amtool e 14 cenários de regras passaram.
Três testes de limites de exposição passaram; quatro dashboards/44 painéis foram
provisionados, 59 queries aceitas e TargetDown chegou ao Alertmanager. O teste
Nginx bloqueou sete variantes do endpoint, preservando health e scrape interno.

A stack **dev** foi executada integralmente. A configuração **prod** foi validada
e sua imagem Nginx foi testada isoladamente; não houve inicialização da stack de
produção nem alteração de seu banco. Para um deploy prod, execute os comandos de
startup/migration do README com `--env-file .env.production -f compose.prod.yaml`,
desative antes o Node Exporter dev no mesmo bind e repita a validação interna.

Não há histórico de 30 dias suficiente para comprovar SLO. Não há integração
externa de notificações, HA, probes externos de disponibilidade, reconciliação de
incidentes abertos nem tamanho de writable layer confiável neste driver.
Loki/Promtail/OTel/Tempo/Jaeger, SLA contratual, Kubernetes, Helm, Argo CD e GitOps
permanecem fora da v1.1. Nenhum commit, push, PR, merge ou tag faz parte desta entrega.
