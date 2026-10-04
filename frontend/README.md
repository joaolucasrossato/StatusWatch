# StatusWatch Web

Splash da v0.1.0 em React + TypeScript + Vite. Consulte o README da raiz para executar a stack.

```bash
npm ci
npm run dev
npm run lint
npm run build
```

O navegador consulta `/api/health`. O proxy do Vite encaminha para `API_PROXY_TARGET` (padrão local: `http://127.0.0.1:8000`; Compose: `http://api:8000`). Essa variável é do servidor Vite e não contém segredos. `npm run preview` também utiliza o proxy. O container usa o servidor de desenvolvimento nesta fundação v0.1.0.
