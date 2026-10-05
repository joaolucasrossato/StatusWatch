# StatusWatch Web

React + TypeScript + Vite, CSS próprio e Recharts. Interface autenticada para
monitores, dashboard, stats/history, incidentes e notificações por monitor.
Navegação por estado React; JWT apenas em memória; dados sempre vindos da API.

```bash
npm ci
npm run dev
npm test
npm run lint
npm run build
```

Vitest + Testing Library + happy-dom validam interações sem serviços externos.
Polling de monitoramento: 30 segundos enquanto visível. A navegação suspende
polling da tela anterior e os novos componentes cancelam requests ao desmontar.

O navegador acessa `/api`. Vite encaminha para `API_PROXY_TARGET` (padrão local
`http://127.0.0.1:8000`; Compose `http://api:8000`). O Compose de desenvolvimento
usa Vite; produção usa o Dockerfile.prod com Nginx e arquivos compilados.
Consulte o README da raiz e docs/incidents.md e docs/notifications.md.
