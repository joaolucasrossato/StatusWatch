# Arquitetura v0.3.0

```text
Browser → web:5173 (Vite /api proxy) → api:8000 (FastAPI)
                                       ├── db:5432 (PostgreSQL 17)
                                       └── redis:6379 (Redis 7.4)
worker (Python) ────────────────────────┴── mesmas dependências
```

A API mantém um pool SQLAlchemy e um cliente Redis por processo, criados no lifespan e fechados no encerramento. `/health` executa `SELECT 1` e `PING` a cada chamada, sem cache. As operações síncronas da rota são executadas pelo FastAPI em seu pool de threads. Conexão, pool e query têm limites de tempo. Respostas e logs de falha não expõem URLs ou credenciais.

O worker usa as mesmas configurações e conexões, valida ambas na inicialização e permanece bloqueado em `Event.wait()`. SIGTERM/SIGINT liberam a espera e fecham as conexões. Falha inicial de dependência encerra o processo com código 1. O worker não consome filas, não verifica URLs e não anuncia saúde contínua das dependências.

Compose aguarda os healthchecks do PostgreSQL e Redis antes de iniciar API/worker; web aguarda a API. Essa ordenação vale para a inicialização, não reinicia consumidores quando uma dependência falha posteriormente. A API reflete falhas em `/health` e pode voltar a responder saudável após a recuperação.

A rede bridge é privada ao projeto, com apenas web e API publicados no loopback do host. O volume `postgres_data` persiste o PostgreSQL. Redis não exige persistência nesta versão. Vite é usado para desenvolvimento. Em produção, Nginx serve o bundle React e encaminha /api à API privada. Somente o frontend é publicado no loopback.

A autenticação usa JWT e Argon2. Sessions ORM síncronas são injetadas por request. Alembic cria users e monitors; cada monitor pertence a um usuário, e todas as consultas CRUD aplicam ownership. O frontend mantém o token em memória. Monitores são apenas configurações: não há execução de checks nesta versão.
