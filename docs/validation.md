# Validação da v0.1.0

Executada em 04/10/2026.

Registro histórico preservado. Consulte [validação v1.0](validation-v1.0.md) para a consolidação atual.

- `npm run lint`: aprovado.
- `npm run build`: aprovado (TypeScript e build Vite).
- `python3 -m compileall -q backend/app backend/tests`: aprovado.
- `docker compose config --quiet`: aprovado.
- `docker compose up --build -d --wait`: imagens construídas e cinco serviços iniciados.
- PostgreSQL, Redis e API: healthchecks saudáveis.
- GET `/`: HTTP 200 com nome e versão esperados.
- GET `/health`: HTTP 200 com API, PostgreSQL e Redis saudáveis.
- GET `http://127.0.0.1:5173/api/health`: HTTP 200 através do proxy Vite.
- Redis parado temporariamente: HTTP 503, `services.redis=unhealthy`.
- PostgreSQL parado temporariamente: HTTP 503, `services.database=unhealthy`.
- Dependências restauradas: HTTP 200 novamente, sem reiniciar a API.
- Navegador: splash renderizada, estado Online, estado Offline com Redis parado e recuperação automática para Online.
- Worker: logs de conexão OK para PostgreSQL e Redis; encerramento por SIGTERM com código 0; reiniciado com sucesso.
- `.env`, `.venv`, node_modules e dist: ignorados pelo Git; nenhuma `.venv` criada pelo projeto.

## Testes unitários

12 testes aprovados em container Python 3.12 descartável. O host não tinha pip instalado. Comando executado na raiz:

```bash
docker run --rm --user root \
  -v "$PWD/backend:/tests:ro" -w /tests statuswatch-api \
  sh -c 'pip install --no-cache-dir -r requirements-dev.txt >/tmp/pip-test.log && python -m pytest -q -p no:cacheprovider'
```

Houve um `DeprecationWarning` de Starlette/AnyIO sobre o alias `BlockingPortal`, sem falhas. Os testes unitários usam mocks; as conexões reais foram verificadas separadamente no Compose.

## Limites

A validação visual foi feita no navegador desktop; não houve matriz de browsers/dispositivos. O container web usa Vite de desenvolvimento. O worker verifica as dependências apenas na inicialização. Essas escolhas correspondem ao escopo da v0.1.0.
