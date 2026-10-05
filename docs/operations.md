# Operação e recuperação — v1.0

Execute injeção de falhas somente em ambiente de desenvolvimento/descartável.
Não execute `down -v` nem downgrade no banco real. Faça backup antes de migrations.
Use os Compose da raiz; os fragmentos antigos em `backend/` não são entrypoints.

## Validação reproduzível

```bash
docker compose config --quiet
docker compose up -d db redis
docker compose build api worker web
docker compose run --rm api alembic upgrade head
docker compose up -d --wait
docker compose exec api alembic current
docker compose exec api alembic heads
docker compose exec api alembic check
curl -f http://localhost:8000/
curl -f http://localhost:8000/health
curl -f http://localhost:5173/api/health
python3 backend/tests/smoke_monitors.py http://localhost:8000
python3 backend/tests/smoke_engine.py http://localhost:8000
```

Os smokes HTTP criam contas sintéticas (ficam no banco de desenvolvimento),
removem seus monitores e não precisam de serviços públicos. O engine usa uma URL
loopback que deve ser bloqueada antes da rede. Confirma checks, dashboard, history,
stats e pausa.

Testes PostgreSQL isolados criam e removem somente bancos com UUID gerado pelo
script (role precisa de CREATEDB):

```bash
docker compose run --rm -v "$PWD/backend/tests:/validation:ro" api python /validation/validate_migrations.py
docker compose run --rm -v "$PWD/backend/tests:/validation:ro" api python /validation/validate_notifications.py
```

O segundo verifica UP/DOWN/DOWN/DOWN/DOWN/UP/UP, um único incidente, outbox única,
claims concorrentes, falha/retry/sucesso, envio sem conexão ocupada e retenção.
SMTP/webhook são substituídos por transportes de teste; não enviam mensagens reais.

## Redis down/recovery

```bash
docker compose stop redis
curl -i http://localhost:8000/health
docker compose start redis
```

Esperado: 503 com redis unhealthy, depois 200. Redis não é fila nem lock do
scheduler; checks já iniciados continuam. Na inicialização, o worker exige Redis
saudável. Compose reinicia o worker em falhas, a menos que tenha sido parado
explicitamente.

## PostgreSQL unavailable/recovery

```bash
docker compose stop db
curl -i http://localhost:8000/health
docker compose start db
```

Esperado: 503 no health e nas rotas que recebem OperationalError; nenhum SQL ou
credencial no corpo. Scheduler e entregas registram falha e tentam no próximo
ciclo; pool_pre_ping descarta conexões antigas. Após recuperação, health volta a
200 e checks voltam a avançar sem reiniciar API. Resultados HTTP cuja persistência
falhou não são recuperados; o monitor permanece due. Cleanup tenta novamente na
próxima hora.

## Worker restart e sinais

```bash
docker compose restart worker
docker compose logs --tail 30 worker
```

Esperado: stopped/ready, novos checks respeitando o último timestamp persistido.
SIGTERM/SIGINT cancelam tarefas e fecham conexões; Docker concede 15 segundos.
SMTP síncrono tem timeout de socket de 10 segundos, mas uma sessão com várias
operações pode exceder o período de parada. Se houver encerramento forçado, o
lease da entrega expira em 5 minutos e outro ciclo pode retomá-la. Envio externo
é at-least-once: deduplicar `Idempotency-Key` no receptor.

## Webhook timeout, SMTP failure e retries

Na suíte local, execute:

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_notification_senders.py tests/test_notification_outbox.py tests/test_worker.py tests/test_retention.py
```

Transportes simulados cobrem timeout, recusa SMTP, HTTP malformado, bloqueios SSRF,
erros sanitizados e recovery de claim abandonado. São três tentativas totais,
esperas de 60 e 300 segundos; na terceira falha o status é FAILED. Não há replay
manual. Falha de envio não interrompe o scheduler. Em um laboratório SMTP vazio,
crie canal EMAIL de teste e produza incidente: `smtp_not_configured` deve aparecer
sem impedir novos checks. Nunca use um canal real para injeção de falhas.
