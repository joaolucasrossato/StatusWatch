# Validação v0.3.0 — 2026-10-04

Branch: `feature/monitors-v0.3`. Sem commit, push ou merge.

## Auditoria inicial

Working tree limpa na main. Autenticação v0.2 com JWT/Argon2, SQLAlchemy síncrono, UUID PostgreSQL, timestamps server-default e onupdate=now(), migration users `4bffcd0e1da1`. Frontend era uma página de saúde da API. Não havia testes de autenticação. O teste de versão ainda esperava 0.1.0, embora a API já estivesse na v0.2.0. Nenhum AGENTS.md encontrado.

A primeira tentativa de pytest não executou por ausência de pytest no virtualenv. Instalado `requirements-dev.txt`, sem novas dependências no projeto. TestClient ficou bloqueado na sandbox; execução fora dela funcionou. A execução inicial efetiva teve 11 testes passando e uma falha na expectativa antiga de versão, posteriormente corrigida. O primeiro build TypeScript identificou uma parameter property incompatível com erasableSyntaxOnly, corrigida. Tentativas de npm/pytest na raiz foram corrigidas para os diretórios backend/frontend. Os resultados finais abaixo substituem essas tentativas.

## Comandos e resultados finais

Executados a partir da raiz, exceto pytest no backend e npm no frontend.

| Comando | Resultado |
| --- | --- |
| `cd backend && .venv/bin/python -m pytest -q` | PASS — 84 testes; um warning de depreciação Starlette/AnyIO |
| `backend/.venv/bin/python -m compileall -q backend/app backend/alembic backend/tests` | PASS |
| `cd frontend && npm run lint` | PASS — sem warnings |
| `cd frontend && npm run build` | PASS — TypeScript e Vite |
| `docker compose config --quiet` | PASS |
| `docker compose build api worker` | PASS |
| `docker compose up -d db redis` | PASS |
| `docker compose run --rm api alembic upgrade head` | PASS — 4bffcd0e1da1 → 9d2f3a7c8b10 |
| `docker compose run --rm api alembic current` | PASS — 9d2f3a7c8b10 (head) |
| `docker compose run --rm api alembic heads` | PASS — um head |
| `docker compose run --rm api alembic check` | PASS — sem operações pendentes |
| `docker compose run --rm -v "$PWD/backend/tests/validate_migrations.py:/tmp/validate_migrations.py:ro" api python /tmp/validate_migrations.py` | PASS — banco descartável: upgrade, downgrade -1, upgrade, check; usuário preservado |
| `docker compose up -d --build --wait` | PASS — builds api/worker/web |
| `docker compose ps` | PASS — API/db/Redis healthy; web/worker running (sem healthcheck próprio) |
| `docker compose logs --tail 8 worker` | PASS — PostgreSQL OK, Redis OK, worker ready |
| `python3 backend/tests/smoke_monitors.py http://127.0.0.1:8000` | PASS — HTTP real direto |
| `python3 backend/tests/smoke_monitors.py http://127.0.0.1:5173/api` | PASS — proxy Vite |
| `python3 backend/tests/smoke_monitors.py http://127.0.0.1:18080/api` | PASS — proxy Nginx/produção isolada |
| `curl -fsS http://127.0.0.1:18080/healthz` | PASS — ok |
| `curl -fsS http://127.0.0.1:18080/` | PASS — HTML frontend |
| `git diff --check` | PASS |
| `git check-ignore .env .env.production` | PASS — ambos ignorados |
| `git diff --cached --stat` | PASS — nada staged |

O smoke HTTP verifica register/login/me, /health, criação/leitura/listagem/edição/exclusão, timestamps com timezone, validações 422, token ausente/inválido 401 e isolamento com dois usuários: GET/PATCH/DELETE alheio 404 e lista sem vazamentos. Usa contas sintéticas únicas e remove os monitores que cria; as contas de smoke ficam no banco de desenvolvimento.

Pytest usa SQLite temporário com FK ativada e autenticação real, sem conexão com dados reais. PostgreSQL foi validado separadamente pelas migrations e pelos testes HTTP. Nenhum teste consulta a URL de um monitor.

## Produção isolada

Prefixo dos comandos executados:

```bash
docker compose --env-file /tmp/statuswatch-v03-prod.env \
  -f compose.prod.yaml -f /tmp/statuswatch-v03-prod-override.yaml \
  -p statuswatch-v03-validation
```

Executados com esse prefixo, todos PASS: `config --quiet`, `build api worker web`, `run --rm api alembic upgrade head`, `up -d --wait`, `run --rm api alembic check`, `ps`.

Secrets novos gerados apenas para esse laboratório, sem imprimir valores e sem reutilizar secrets de desenvolvimento. Override somente para volume `statuswatch_v03_validation_postgres_data` e frontend em `127.0.0.1:18080`. Nenhum acesso ao volume `statuswatch_prod_postgres_data`. API/db/Redis sem portas publicadas. API/db/Redis/web ficaram healthy; worker running com inicialização válida. Stack temporária removida ao fim da validação, junto com seu volume e secrets temporários; stack de desenvolvimento preservada.

## Navegador

Verificados na interface real: cadastro de usuário sintético, login, loading, estado vazio, criação, pausa, edição (intervalo 300 / timeout 20), reativação e abertura/cancelamento da confirmação de exclusão. Exclusão efetiva validada por HTTP e pytest. Inspeção visual confirmou listagem com Active/Paused e painel System Status separado. Um monitor sintético de UI foi mantido na conta de teste local.

## Segurança e limites

Models/registry e ownership revisados. Nenhuma alteração na migration users, JWT dependency ou algoritmo de autenticação. Campos extras/imutáveis e null em PATCH rejeitados. HTTP/HTTPS via HttpUrl, GET via Literal. Queries de CRUD parametrizadas pelo SQLAlchemy; identificadores do banco temporário escapados com psycopg.sql.Identifier.

Nenhum novo secret real adicionado, nenhum arquivo staged, `.env` e `.env.production` ignorados. A auditoria encontrou um JWT_SECRET preexistente no `.env.example` versionado, igual ao secret local. Foi removido do exemplo e substituído por placeholder; `.env` real e histórico Git não foram alterados. O valor antigo ainda existe no histórico e precisa ser rotacionado antes de uso fora do laboratório. Exemplos e testes usam placeholders ou credenciais sintéticas. Sem paginação, refresh token ou persistência de sessão no navegador. Após reload é necessário novo login. Não há testes automatizados de browser adicionados; o fluxo foi validado interativamente. O warning de depreciação existente do TestClient não impede os testes.

Checks HTTP e proteção SSRF completa, scheduler, histórico, uptime, latência, incidentes, alertas, planos, observabilidade e Kubernetes continuam para v0.4+.

## Inventário final de arquivos

`M`: modificado; `??`: criado, ainda não staged.

```text
 M .env.example
 M README.md
 M backend/alembic/env.py
 M backend/app/main.py
 M backend/app/models/__init__.py
 M backend/app/models/user.py
 M backend/tests/conftest.py
 M backend/tests/test_api.py
 M docs/architecture.md
 M frontend/package-lock.json
 M frontend/package.json
 M frontend/src/App.css
 M frontend/src/App.tsx
?? backend/alembic/versions/9d2f3a7c8b10_create_monitors_table.py
?? backend/app/api/routes/monitors.py
?? backend/app/models/monitor.py
?? backend/app/schemas/monitor.py
?? backend/app/services/monitors.py
?? backend/tests/smoke_monitors.py
?? backend/tests/test_auth.py
?? backend/tests/test_monitors.py
?? backend/tests/validate_migrations.py
?? docs/monitors.md
?? docs/validation-v0.3.md
?? frontend/src/AuthForm.tsx
?? frontend/src/MonitorForm.tsx
?? frontend/src/Monitors.tsx
?? frontend/src/api.ts
```

Sugestão de commit, não executado: `feat: add monitor management`.
