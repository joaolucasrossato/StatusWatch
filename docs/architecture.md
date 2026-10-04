# Arquitetura v0.4.0

```text
Usuário → React/Vite ou Nginx → FastAPI → PostgreSQL
                                  │         ↑
                                Redis       │
                                            │
Worker → scheduler → checker HTTP → MonitorCheck
                           ↓
                     Destino público
```

API mantém JWT/Argon2 e CRUD com ownership. SQLAlchemy é síncrono; API usa pool de threads do FastAPI e worker usa operações curtas via asyncio.to_thread, sem banco aberto durante rede. Alembic registra User, Monitor e MonitorCheck pelo registry de models.

Worker é processo separado, valida PostgreSQL/Redis no startup, mantém AsyncClient e agenda checks pela última data persistida. Concorrência limitada e shutdown por SIGTERM/SIGINT. Redis continua disponível com health probe, sem queue. Somente uma réplica de scheduler; múltiplas réplicas podem duplicar checks.

Produção usa Nginx como gateway /api, API/db/Redis privados. Rede bridge com saída permite checks externos. Compose aguarda dependências saudáveis no startup; healthchecks não representam saúde contínua do scheduler. Não há endpoint HTTP no worker.

Frontend mantém JWT em memória e distingue configuração Active/Paused de resultado UP/DOWN/Pending. O painel System Status continua medindo a saúde da própria plataforma.

Fluxos, segurança SSRF, dados, consultas e limites: [monitoring-engine.md](monitoring-engine.md).
