# Validação StatusWatch v1.0.0

Data: 05/10/2026 (America/Sao_Paulo). Base: main, commit 6a8d65a.
Working tree inicialmente limpo; sem AGENTS.md aplicável ao projeto.

## Baseline antes das alterações

- Versão atual 0.6.0 em README/API/frontend, apesar de Notifications implementada.
  Foi alinhada primeiro a 0.7.0; documentos históricos v0.x preservados.
- `python3 -m pytest -q`: Python do sistema sem pytest. `.venv` existente usada.
  TestClient bloqueou no sandbox; execução local com permissão passou:
  **268 passed**, um DeprecationWarning Starlette/AnyIO, 93,35 s.
- compileall e git diff --check passaram.
- Frontend: **11 testes**, lint e build passaram. Warning de bundle >500 kB.
- Compose config válido. Docker inicialmente sem serviços; acesso ao daemon
  exigiu permissão do ambiente. Após iniciar db/redis, baseline em container
  temporário: current=head=f7a10d92c630, único head, alembic check sem divergência.

## Alterações e testes

- Retenção configurável, tarefa horária independente, índices por data.
- Cleanup testa limites exatos, configuração, SENT/FAILED versus PENDING/PROCESSING,
  preservação de incidentes, idempotência, rollback dos dois DELETEs e recovery.
- JWT valida secret/algoritmo/TTL e exige exp/sub/type; testes de token sem exp e
  expirado. 422 não ecoa senha; indisponibilidade do banco retorna 503 sanitizado.
- DNS de canais fora da transação, revalidação de ownership após DNS, teste dedicado.
- Histórico/dashboard usam desempate por UUID consistente com último check.
- Frontend: polling health 30 s e aba visível, cleanup do timer, erro 5xx genérico,
  card Active, label UP, captions nas tabelas de notificações.
- Recovery de delivery_loop após erro de banco e falhas explícitas SMTP/webhook.
- Logs monitor_check_completed, incident_opened/resolved após commit e cleanup.
- Pins das dependências diretas previamente abertas; headers Nginx e restart dev.

A primeira execução da nova suíte teve quatro falhas na preparação dos dados de
retenção: rows() chamava expire_all e descartava datas alteradas antes do commit.
A ordem foi corrigida, sem remover testes ou enfraquecer asserts. A suíte seguinte
passou com 286 testes; quatro casos de transporte foram acrescentados em seguida.

## Validação integrada executada

- Stack dev: cinco serviços UP; api/db/redis healthy (web/worker não têm probe).
- Root, health direto e health via Vite: HTTP 200.
- Smoke HTTP: register/login/me, CRUD, validação, timestamps, ownership com dois
  usuários, Pending → DOWN/ssrf_blocked pelo worker, dashboard/history/stats,
  incident API e pausa preservada além do intervalo.
- Migration a81d4e29b607: upgrade em banco descartável, downgrade dos índices e da
  etapa Notifications, usuários/monitores preservados, re-upgrade e metadata check.
- current=head=a81d4e29b607, único head, `No new upgrade operations detected.`
- PostgreSQL descartável: sequência UP/DOWN/DOWN/DOWN/DOWN/UP/UP verificada a cada
  etapa, exatamente um incidente e duas entregas, constraint de duplicidade,
  claims concorrentes, retry e envio após commit sem conexão ocupada.
- Cleanup real no PostgreSQL removeu sete checks e duas entregas terminais,
  preservando o incidente.
- Imagens de produção construídas; stack separada em 18080 e volume exclusivo.
  Nginx/API/db/redis healthy, worker running; headers nosniff/DENY/no-referrer.
- Injeção real de falhas isolada: Redis down/recovery e PostgreSQL down/recovery
  retornaram 503/200; restart do worker passou. Smokes HTTP também via Nginx.
- Nenhum SMTP/webhook real usado nos testes de envio; transportes simulados.

## Reproduzir o laboratório de produção

Além de `.env` válido para o laboratório, crie `/tmp/statuswatch-v1-prod.yaml`:

```yaml
services:
  api:
    environment:
      APP_ENV: production
  worker:
    environment:
      APP_ENV: production
  web:
    ports: !override
      - "127.0.0.1:18080:80"
volumes:
  postgres_data:
    name: statuswatch_v1_validation_data
```

Use `docker compose -p statuswatch-v1-validation -f compose.prod.yaml -f
/tmp/statuswatch-v1-prod.yaml` como prefixo para `build`, `up -d db redis`,
`run --rm api alembic upgrade head` e `up -d --wait`.
Depois execute `python3 backend/tests/validate_recovery.py` da raiz.
O script é fixado nesse projeto descartável. Para os smokes, passe
`http://127.0.0.1:18080/api`. Ao terminar, use o mesmo prefixo e `down -v` **somente
nesse laboratório**; o volume de produção statuswatch_prod_postgres_data não é usado.

## Limitações e classificação de warnings

- DeprecationWarning Starlette/AnyIO: compatibilidade futura, sem falha funcional;
  atualização coordenada documentada em security.md.
- Vite bundle ~606 kB minificado: aviso de performance, sem erro de compilação;
  divisão do bundle pode ser feita depois, sem alterar o design.
- `npm audit` zero; pip-audit reporta 16 entradas/8 advisories únicos em
  Starlette e pytest. Aplicabilidade, versões corrigidas e decisões em
  [security.md](security.md). Não é uma certificação de ausência de vulnerabilidades.
- Sem matriz visual de browsers, teste de carga, entrega SMTP real ou firewall
  de provedor. Componentes React têm testes; APIs/proxies têm smokes HTTP.
- Scheduler de uma réplica, destino em texto claro no banco, at-least-once,
  imagens/transitivas sem lock integral e efeitos da retenção após pausas longas
  documentados. Secret antigo registrado no histórico exige rotação fora do laboratório.

## Resultado final após bump

- Backend: **290 passed**, 1 warning, 186,03 s. Nenhum skip.
- Frontend: **13 passed** em quatro arquivos; lint e build aprovados.
- compileall e git diff --check aprovados.
- Compose dev/prod config aprovado; rebuild dev 1.0.0 com cinco serviços UP,
  api/db/redis healthy. Root confirma 1.0.0; ambos os health endpoints retornam 200.
- Alembic current=head=a81d4e29b607, um head, sem operações novas.
- Smokes HTTP completos repetidos após bump: auth/CRUD/ownership, worker,
  dashboard/history/stats e pausa aprovados.
- Revisão das versões antigas: somente docs históricos e requisito de versão
  Node de dependência no lock; versões atuais todas 1.0.0.
- Laboratório de produção e volume exclusivo removidos após os testes;
  stack de desenvolvimento mantida ligada. Banco de produção não utilizado.
- Alterações organizadas em commits locais; sem push, tag ou merge. Nenhum .env,
  credential, venv, node_modules ou temporário incluído.

A consolidação está validada localmente. Isso não elimina as limitações de
segurança/deploy explicitadas acima; os advisories pendentes permanecem visíveis.
