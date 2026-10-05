# StatusWatch · v1.0.0

StatusWatch é uma plataforma de monitoramento HTTP/HTTPS desenvolvida como
projeto de portfólio com foco em backend, infraestrutura, DevOps,
observabilidade e SRE.

A versão **v1.0.0** consolida monitoramento, incidentes e notificações
com outbox transacional, retries, retenção e procedimentos de recuperação.

Nesta versão, o usuário pode:

- criar e gerenciar monitores HTTP/HTTPS;
- ativar e pausar monitoramento;
- acompanhar o último estado operacional de cada monitor;
- visualizar um dashboard consolidado;
- consultar estatísticas das últimas 24 horas;
- visualizar uptime e tempos de resposta;
- acompanhar gráfico de response time;
- consultar o histórico recente de checks;
- acompanhar incidentes globais e por monitor com filtros e paginação;
- configurar canais EMAIL/WEBHOOK por monitor e consultar entregas.

O worker executa os checks em segundo plano e persiste seus resultados no
PostgreSQL. A API disponibiliza os dados ao frontend autenticado via JWT.

> **Importante:** `Active/Paused` representa o estado de monitoramento.
> `UP/DOWN` representa o último resultado operacional do serviço.
> Um monitor ativo que ainda não possui checks é apresentado como `Pending`.

## Arquitetura e stack

```text
                    ┌─────────────────────┐
                    │ React + TypeScript  │
                    │ Vite + Recharts     │
                    │       :5173         │
                    └──────────┬──────────┘
                               │ /api
                               ▼
                    ┌─────────────────────┐
                    │      FastAPI        │
                    │       :8000         │
                    └──────┬───────┬──────┘
                           │       │
                           ▼       ▼
                    PostgreSQL   Redis
                        17        7.4
                           ▲       ▲
                           └───┬───┘
                               │
                    ┌──────────┴──────────┐
                    │   Python Worker     │
                    │ HTTP Check Engine   │
                    └─────────────────────┘
```

## Requisitos

Para a stack: Docker Engine/Desktop ativo e Docker Compose v2 ou superior. Portas 5173 e 8000 livres. Para desenvolvimento fora de containers: Python 3.12 e Node 22.12+ com npm.

## Configuração e execução com Docker

Na raiz:

```bash
cp .env.example .env
# Edite .env antes de usar credenciais diferentes das de exemplo.
docker compose config --quiet
docker compose build api worker
docker compose up -d db redis
docker compose run --rm api alembic upgrade head
docker compose up --build
```

Acesse:

- Frontend: http://localhost:5173
- API: http://localhost:8000
- Health: http://localhost:8000/health
- Swagger: http://localhost:8000/docs

Os containers são `statuswatch-web`, `statuswatch-api`, `statuswatch-worker`, `statuswatch-db` e `statuswatch-redis`. PostgreSQL e Redis não publicam portas no host. API e web são publicados somente em `127.0.0.1` para desenvolvimento local.

### Variáveis

| Variável | Uso |
| --- | --- |
| `APP_NAME` | Nome da aplicação nos logs (padrão StatusWatch) |
| `APP_ENV` | Identificação do ambiente (development nesta versão) |
| `POSTGRES_DB` | Banco inicial, statuswatch |
| `POSTGRES_USER` | Usuário inicial, statuswatch |
| `POSTGRES_PASSWORD` | Senha inicial do PostgreSQL |
| `DATABASE_URL` | URL SQLAlchemy com driver `postgresql+psycopg` |
| `REDIS_URL` | URL Redis |
| `JWT_SECRET` | Secret JWT obrigatório (mínimo 32 caracteres); use valor aleatório e diferente por ambiente |
| `JWT_ALGORITHM` | Algoritmo JWT, padrão HS256 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Validade do token, padrão 60 minutos |
| `WORKER_MAX_CONCURRENCY` | Máximo de checks simultâneos, padrão 10 |
| `WORKER_POLL_INTERVAL_SECONDS` | Pausa entre ciclos, padrão 5 segundos |
| `WORKER_MAX_REDIRECTS` | Máximo de redirects validados, padrão 5 |
| `CHECK_RETENTION_DAYS` | Dias de checks retidos (1–3650), padrão 30 |
| `NOTIFICATION_RETENTION_DAYS` | Dias de entregas SENT/FAILED retidas (1–3650), padrão 30 |
| `SMTP_HOST`, `SMTP_PORT` | Servidor SMTP opcional, porta padrão 587 |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Credenciais SMTP via ambiente |
| `SMTP_FROM`, `SMTP_USE_TLS` | Remetente e STARTTLS (padrão true) |
| `API_PROXY_TARGET` | Destino do proxy Vite; definido no Compose como `http://api:8000` |

`change_me` é apenas um placeholder de desenvolvimento. Mantenha a senha de `DATABASE_URL` consistente com `POSTGRES_PASSWORD`. Caracteres especiais na URL precisam de percent-encoding. `.env` é ignorado pelo Git e não entra nas imagens. Não compartilhe a saída de `docker compose config` com valores reais, pois ela contém as variáveis resolvidas.

Entre containers, os hosts são `db`, `redis` e `api`, nunca localhost. `Settings` centraliza as variáveis do processo; Docker Compose carrega o `.env` e as injeta nos containers. As tabelas `users`, `monitors`, `monitor_checks`, `incidents`, `notification_channels` e `notification_deliveries` são criadas por migrations Alembic, aplicadas explicitamente antes de iniciar a aplicação.

## Desenvolvimento local

### PostgreSQL e Redis

Para executar API/worker no host, publique temporariamente as dependências no loopback usando um override local:

```bash
docker compose up -d db redis
cat > /tmp/statuswatch-local.yaml <<'YAML'
services:
  db:
    ports:
      - "127.0.0.1:5432:5432"
  redis:
    ports:
      - "127.0.0.1:6379:6379"
YAML
docker compose -f compose.yaml -f /tmp/statuswatch-local.yaml up -d db redis
```

Alternativamente, utilize instalações locais de PostgreSQL 17 e Redis. O override acima usa sintaxe de shell POSIX; no Windows crie manualmente o mesmo YAML e ajuste o caminho. Pare API/web do Compose se já estiverem usando as portas locais: `docker compose stop api web worker`.

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://statuswatch:change_me@127.0.0.1:5432/statuswatch'
export REDIS_URL='redis://127.0.0.1:6379/0'
# Defina JWT_SECRET com um valor aleatório local antes de executar.
alembic upgrade head
uvicorn app.main:app --reload
```

Adapte as credenciais à configuração do banco. A `.venv` é criada manualmente pelo desenvolvedor, nunca pelo projeto, e não é versionada. No Windows/PowerShell, ative com `.venv\Scripts\Activate.ps1` e defina variáveis com `$env:DATABASE_URL = '...'` e `$env:REDIS_URL = '...'`. Fora do Compose, exporte também JWT_SECRET no terminal; não use secrets reais em comandos versionados.

Em outro terminal, com o mesmo ambiente e variáveis:

```bash
cd backend
source .venv/bin/activate
python -m app.worker
```

O worker valida as conexões, anuncia `ready` e agenda checks de monitores ativos com intervalos configurados. Ctrl+C ou SIGTERM encerra as conexões de forma limpa. Se uma dependência falhar no início, sai com código 1; reinicie depois de corrigir a conexão.

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

O proxy local usa `http://127.0.0.1:8000`. Para outro destino, defina `API_PROXY_TARGET` no ambiente do Vite. O navegador acessa `/api/health` na mesma origem, sem precisar configurar CORS. Consulta ao carregar e novamente 30 segundos após cada verificação, somente enquanto a aba está visível; timeout de 10 segundos. HTTP 503, resposta inválida ou falha de rede exibem `API Offline`, que significa que a API **ou uma dependência** não está saudável. O estado inicial é “Verificando API…”.

## Endpoints

| Método | Caminho |
| --- | --- |
| POST | `/auth/register` |
| POST | `/auth/login` |
| GET | `/auth/me` |
| GET | `/monitors` |
| POST | `/monitors` |
| GET | `/monitors/{monitor_id}` |
| PATCH | `/monitors/{monitor_id}` |
| DELETE | `/monitors/{monitor_id}` |
| GET | `/monitors/{monitor_id}/checks/latest` |
| GET | `/dashboard/summary` |
| GET | `/monitors/{monitor_id}/checks` |
| GET | `/monitors/{monitor_id}/stats` |
| GET | `/incidents` |
| GET | `/incidents/{incident_id}` |
| GET | `/monitors/{monitor_id}/incidents` |
| GET | `/notification-channels` |
| POST | `/notification-channels` |
| GET | `/monitors/{monitor_id}/notification-channels` |
| PATCH | `/notification-channels/{channel_id}` |
| DELETE | `/notification-channels/{channel_id}` |
| GET | `/notification-deliveries` |
| GET | `/incidents/{incident_id}/notification-deliveries` |
| GET | `/` |
| GET | `/health` |

`GET /` retorna `{"name":"StatusWatch","version":"1.0.0"}`. Swagger: `/docs`; schema: `/openapi.json`.

Exemplo saudável:

```json
{"status":"healthy","services":{"api":"healthy","database":"healthy","redis":"healthy"}}
```

Os probes executam `SELECT 1` e `PING` reais. A API pode estar acessível mesmo retornando 503; `services.api` representa essa disponibilidade. Os testes unitários substituem conexões externas para funcionar sem containers ou credenciais.

## Validação

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -q
cd ../frontend
npm test
npm run lint
npm run build
cd ..
docker compose config --quiet
docker compose up --build -d --wait
curl -f http://localhost:8000/
curl -f http://localhost:8000/health
curl -f http://localhost:5173/api/health
docker compose logs worker
```

Os testes cobrem respostas da API, falha de cada dependência, execução dos probes, fechamento de conexões e sinais de encerramento do worker. Teste de integração manual de recuperação (somente no ambiente de desenvolvimento):

```bash
docker compose stop redis
curl -i http://localhost:8000/health  # HTTP 503, redis unhealthy
docker compose start redis
curl -i http://localhost:8000/health  # HTTP 200 após recuperação
```

Registro histórico: [docs/validation.md](docs/validation.md). Validação da consolidação: [docs/validation-v1.0.md](docs/validation-v1.0.md).

## Comandos úteis

```bash
docker compose ps
docker compose logs -f
docker compose logs api
docker compose logs worker
docker compose stop worker
docker compose start worker
docker compose down
```

`docker compose down` preserva o banco no volume nomeado. `docker compose down -v` **apaga os dados**; use apenas para reinicializar intencionalmente o ambiente de desenvolvimento.

## Troubleshooting

- **Variável obrigatória ausente:** copie `.env.example` para `.env` na raiz e confira URLs e senha.
- **Porta ocupada:** pare o processo concorrente ou ajuste as portas publicadas no Compose.
- **Docker permission denied:** confira se Docker está ativo e se seu usuário possui permissão de acesso ao daemon.
- **API Offline / HTTP 503:** consulte `/health`, `docker compose ps` e os logs. Confirme `db:5432` e `redis:6379` nos containers, ou loopback e portas publicadas no desenvolvimento local.
- **Mudança de senha sem efeito:** as variáveis `POSTGRES_*` inicializam apenas um volume vazio. Um banco existente mantém suas credenciais; altere-as no banco ou reinicialize conscientemente o volume.
- **Worker terminou:** verifique dependências e execute `docker compose start worker`. Consulte os logs de inicialização e execução do scheduler.
- **Frontend no container:** utiliza Vite para desenvolvimento. O build é validado na imagem, mas esta configuração ainda não é uma publicação de produção.

## Roadmap

Implementado:

- v0.1 Foundation
- v0.2 Authentication
- v0.3 Monitor Management
- v0.4 Monitoring Engine
- v0.5 Dashboard + History
- v0.6 Incidents
- v0.7 Notifications

- v1.0 Stable Release — consolidação, retenção e recuperação.

Próximas versões: Observability, SLO/SLA, Error Budget, Public Status Pages,
Kubernetes e GitOps. Nenhuma dessas etapas está implementada nesta release.



## Monitor Management

- Create monitor, list monitors, get monitor, update monitor e delete monitor.
- Per-user ownership: JWT obrigatório e isolamento por usuário; recursos alheios retornam 404.
- URL validation: somente HTTP/HTTPS; method GET.
- Configurable check interval: 30, 60, 300 ou 600 segundos.
- Configurable timeout: 1–30 segundos, padrão 10.
- Active/paused configuration: habilitação da configuração, sem indicar disponibilidade do serviço.

A interface permite cadastro, login, adicionar/editar monitores, pausar/ativar e excluir com confirmação. O Bearer token fica somente em memória; recarregar a página exige novo login. Não há JWT nem secrets no bundle. Os estados de loading, lista vazia e erros são exibidos na página. O painel System Status continua consultando exclusivamente a saúde da própria API e suas dependências.

| Método | Caminho | Sucesso |
| --- | --- | --- |
| POST | `/auth/register` | 201 |
| POST | `/auth/login` | 200 |
| GET | `/auth/me` | 200 |
| POST | `/monitors` | 201 |
| GET | `/monitors` | 200 |
| GET | `/monitors/{id}` | 200 |
| PATCH | `/monitors/{id}` | 200 |
| DELETE | `/monitors/{id}` | 204 sem body |
| GET | `/monitors/{id}/checks/latest` | 200 com último check ou null (Pending) |

Contrato de configuração v0.3: [docs/monitors.md](docs/monitors.md). Autenticação: [docs/authentication.md](docs/authentication.md). Evidências v0.3: [docs/validation-v0.3.md](docs/validation-v0.3.md).

### Produção

Use `docker compose --env-file .env.production -f compose.prod.yaml`, configurando secrets exclusivos de produção. Execute `build`, `up -d db redis`, `run --rm api alembic upgrade head` e `up -d --wait` com esses mesmos argumentos. O Nginx serve o frontend na porta local 8080 e encaminha `/api/` à API privada. PostgreSQL e Redis não publicam portas. Nunca execute downgrade no banco real para testar migrations; o teste em `backend/tests/validate_migrations.py` cria um banco descartável separado e exige CREATEDB.

## HTTP Monitoring Engine

Async HTTP checks com GET, intervalos configuráveis, timeout total, UP/DOWN, HTTP status code e response time até os headers finais. O worker usa uma réplica, concorrência limitada e decisões baseadas no último check persistido. A interface mostra Latest monitor status (UP/DOWN/Pending) separado de Active/Paused e atualiza a cada 30 segundos enquanto visível. Sem checks artificiais para Pending.

SSRF: bloqueio de destinos não públicos IPv4/IPv6, validação de todos os IPs DNS, pinagem da conexão, TLS verificado e redirects manuais validados. Não substitui controles de egress de rede. Checks têm retenção configurável de 30 dias por padrão. Veja as limitações na documentação do engine.

## Incidentes

Histórico global e por monitor, filtros e paginação, e card de incidentes abertos.
Veja [docs/incidents.md](docs/incidents.md) e [docs/dashboard-history.md](docs/dashboard-history.md).

## Notificações

Nos detalhes de um monitor, abra **Notifications** para criar canais EMAIL ou
WEBHOOK, escolher eventos de abertura/resolução, ativar/desativar e consultar
histórico paginado. Notificações surgem somente nas transições do incidente.

SMTP é opcional. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`,
`SMTP_PASSWORD`, `SMTP_FROM` e `SMTP_USE_TLS` no ambiente e recrie API/worker.
Sem HOST/FROM, emails falham de forma controlada com retries; monitoring continua.
Webhooks devem ser HTTP/HTTPS públicos (prefira HTTPS); destinos privados e
redirects são bloqueados e URLs são mascaradas na API/interface.

O worker executa uma tarefa de entregas independente do scheduler: até três
tentativas com backoff persistido. A outbox compartilha a transação de check e
incidente, mas o envio ocorre depois do commit. A entrega externa é at-least-once;
receptores webhook devem deduplicar pelo header Idempotency-Key.

APIs: `/notification-channels` (GET/POST), `/notification-channels/{id}`
(PATCH/DELETE), `/monitors/{id}/notification-channels` (GET),
`/notification-deliveries` (GET) e `/incidents/{id}/notification-deliveries` (GET).
Todos os recursos são isolados por usuário autenticado.

Documentação completa: [docs/notifications.md](docs/notifications.md).

```bash
# Execute antes de iniciar o código atualizado.
docker compose run --rm api alembic upgrade head
docker compose up --build -d --wait
docker compose exec api alembic current
docker compose exec api alembic heads
docker compose exec api alembic check
cd frontend
npm test
npm run lint
npm run build
```

Retenção e procedimentos operacionais estão descritos abaixo. Criptografia de
destinos com gestão de chaves e replay controlado de entregas ficam para evolução.
Página pública de status, SLO/SLA, billing, Kubernetes e observabilidade externa
continuam fora desta versão.


## Dashboard e histórico

`GET /dashboard/summary` retorna total, active, paused, UP, DOWN, pending,
open_incidents, checks_last_24h e average_response_time_ms_24h. DOWN não é
sinônimo de incidente aberto. Stats sem checks retornam uptime e média null.
History aceita limit/offset; stats aceita window_hours de 1 a 168 (padrão 24).
Todas as consultas são por usuário e retornam Cache-Control: no-store.

## Retention

Cleanup no worker ao iniciar e a cada hora. CHECK_RETENTION_DAYS e
NOTIFICATION_RETENTION_DAYS têm padrão 30 dias; apenas entregas SENT/FAILED são
apagadas. Incidentes e entregas pendentes são preservados. Consulte
[política de retenção](docs/retention.md), incluindo efeito sobre monitores
pausados e janelas de estatísticas.

## Migrations

Execute upgrade antes de iniciar o novo código. A migration de consolidação
`a81d4e29b607` adiciona índices por data; não altera migrations aplicadas.
`alembic current` deve coincidir com o único head e `alembic check` não deve
produzir operações novas. Para banco grande, programe janela para criação dos
índices. [Procedimentos e testes isolados](docs/operations.md).

## Security

SSRF com DNS validado e IP fixado, TLS e validação a cada redirect de checks;
webhooks não seguem redirects. JWT exige secret de pelo menos 32 caracteres e
expiração positiva. URLs de webhook são mascaradas, mas os destinos permanecem
em texto claro no banco. Produção exige secrets próprios, HTTPS no gateway,
proteção de backups e firewall de egress. A auditoria identificou advisories de
Starlette/pytest com upgrades coordenados pendentes; veja a análise de
aplicabilidade e os limites em [docs/security.md](docs/security.md).

Falhas operacionais, restart, SMTP/webhook e retries:
[docs/operations.md](docs/operations.md). Documentos v0.x preservam o contexto
histórico; as políticas atuais de retenção/segurança e este README prevalecem.
