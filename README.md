# StatusWatch · v0.1.0

Fundação de uma plataforma de monitoramento de aplicações, APIs e servidores. Projeto de portfólio focado em backend, DevOps, observabilidade e SRE, com evolução futura para Kubernetes.

Esta versão entrega a integração entre frontend, API, PostgreSQL, Redis e um processo worker. Não realiza monitoramento de URLs nem possui cadastro de monitores.

## Arquitetura e stack

```text
React + TypeScript + Vite :5173
              │ /api/health (proxy Vite)
              ▼
        FastAPI :8000
          │       │
          ▼       ▼
 PostgreSQL 17   Redis 7.4
          ▲       ▲
          └───┬───┘
         Worker Python
```

Python 3.12, FastAPI, Uvicorn, SQLAlchemy, psycopg, redis-py e pydantic-settings. Frontend React com TypeScript e Vite, Node 22. Docker Compose coordena os cinco serviços. Detalhes em [docs/architecture.md](docs/architecture.md).

```text
backend/
  app/
    core/{config,dependencies,logging}.py
    main.py
    worker.py
  tests/
  Dockerfile
  requirements.txt
  requirements-dev.txt
frontend/
  src/{App.tsx,App.css,index.css,main.tsx}
  vite.config.ts
  Dockerfile
  package.json
  package-lock.json
infrastructure/
docs/
compose.yaml
.env.example
.gitignore
```

## Requisitos

Para a stack: Docker Engine/Desktop ativo e Docker Compose v2 ou superior. Portas 5173 e 8000 livres. Para desenvolvimento fora de containers: Python 3.12 e Node 22.12+ com npm.

## Configuração e execução com Docker

Na raiz:

```bash
cp .env.example .env
# Edite .env antes de usar credenciais diferentes das de exemplo.
docker compose config
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
| `API_PROXY_TARGET` | Destino do proxy Vite; definido no Compose como `http://api:8000` |

`change_me` é apenas um placeholder de desenvolvimento. Mantenha a senha de `DATABASE_URL` consistente com `POSTGRES_PASSWORD`. Caracteres especiais na URL precisam de percent-encoding. `.env` é ignorado pelo Git e não entra nas imagens. Não compartilhe a saída de `docker compose config` com valores reais, pois ela contém as variáveis resolvidas.

Entre containers, os hosts são `db`, `redis` e `api`, nunca localhost. `Settings` centraliza a configuração; variáveis do processo têm precedência sobre `.env` no diretório de execução. Nenhuma tabela de negócio é criada nesta versão.

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
uvicorn app.main:app --reload
```

Adapte as credenciais à configuração do banco. A `.venv` é criada manualmente pelo desenvolvedor, nunca pelo projeto, e não é versionada. No Windows/PowerShell, ative com `.venv\Scripts\Activate.ps1` e defina variáveis com `$env:DATABASE_URL = '...'` e `$env:REDIS_URL = '...'`. Também é possível criar `backend/.env` com as URLs locais; ele é ignorado pelo Git.

Em outro terminal, com o mesmo ambiente e variáveis:

```bash
cd backend
source .venv/bin/activate
python -m app.worker
```

O worker registra as conexões, anuncia `ready` e aguarda. Ctrl+C ou SIGTERM encerra as conexões de forma limpa. Se uma dependência falhar no início, sai com código 1; reinicie depois de corrigir a conexão.

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

O proxy local usa `http://127.0.0.1:8000`. Para outro destino, defina `API_PROXY_TARGET` no ambiente do Vite. O navegador acessa `/api/health` na mesma origem, sem precisar configurar CORS. Consulta ao carregar e novamente 15 segundos após cada verificação; timeout de 10 segundos. HTTP 503, resposta inválida ou falha de rede exibem `API Offline`, que significa que a API **ou uma dependência** não está saudável. O estado inicial é “Verificando API…”.

## Endpoints

| Método | Caminho | Resposta |
| --- | --- | --- |
| GET | `/` | 200: `{"name":"StatusWatch","version":"0.1.0"}` |
| GET | `/health` | 200 saudável; 503 se PostgreSQL ou Redis falhar |

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

Registro da execução e limitações: [docs/validation.md](docs/validation.md).

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
- **Worker terminou:** verifique dependências e execute `docker compose start worker`. Nesta versão ele valida apenas a inicialização.
- **Frontend no container:** utiliza Vite para desenvolvimento. O build é validado na imagem, mas esta configuração ainda não é uma publicação de produção.

## Roadmap

Apenas a v0.1.0 está implementada. Evoluções futuras, sem código antecipado nesta entrega: cadastro de monitores e checks HTTP, filas/agendamento, incidentes e notificações, autenticação, observabilidade, SLOs e infraestrutura Kubernetes. A ordem e as versões serão definidas nas próximas etapas.
