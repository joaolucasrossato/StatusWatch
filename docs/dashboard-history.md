# Dashboard e Histórico — v0.5.0

## Visão geral

A versão **v0.5.0** do StatusWatch adiciona a camada de visualização e análise
dos dados produzidos pelo Monitoring Engine implementado na v0.4.

O objetivo desta versão é transformar os checks persistidos pelo worker em
informações úteis para o usuário, mantendo uma separação explícita entre o
estado de configuração do monitor e o estado operacional do serviço.

Principais entregas:

- dashboard consolidado;
- estatísticas por monitor;
- histórico de checks;
- cálculo de uptime;
- métricas de response time;
- página de detalhes do monitor;
- gráfico de response time;
- atualização periódica dos dados no frontend.

---

## Arquitetura

```text
                    ┌───────────────────────┐
                    │       Frontend        │
                    │ React + TypeScript    │
                    │       Recharts        │
                    └───────────┬───────────┘
                                │
                                │ JWT / REST
                                ▼
                    ┌───────────────────────┐
                    │        FastAPI        │
                    ├───────────────────────┤
                    │ Dashboard Service     │
                    │ Monitor History API   │
                    │ Monitor Stats API     │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │     PostgreSQL 17     │
                    ├───────────────────────┤
                    │ monitors              │
                    │ monitor_checks        │
                    └───────────▲───────────┘
                                │
                                │ persiste checks
                                │
                    ┌───────────┴───────────┐
                    │     Python Worker     │
                    │ HTTP Monitoring       │
                    │ Engine                │
                    └───────────────────────┘
```

A v0.5 não adiciona uma nova estrutura de persistência. Os dados são obtidos
das tabelas já utilizadas pelo Monitoring Engine.

Por esse motivo, nenhuma migration adicional foi necessária para esta versão.

---

## Semântica de status

StatusWatch diferencia dois conceitos.

### Estado de monitoramento

Representa se o worker deve executar novos checks.

Valores apresentados no frontend:

- `Active`
- `Paused`

Esse estado é controlado por `monitor.is_active`.

### Estado operacional

Representa o resultado mais recente do serviço monitorado.

Valores:

- `UP`
- `DOWN`
- `Pending`

`UP` e `DOWN` são obtidos do último check persistido.

`Pending` não é persistido como um check. Ele é um estado derivado para um
monitor ativo que ainda não possui nenhum resultado.

### Monitor pausado

Quando um monitor é pausado:

- novos checks deixam de ser executados;
- o monitor passa a contar como `Paused`;
- o último resultado operacional permanece armazenado;
- o dashboard não contabiliza esse monitor como `UP`, `DOWN` ou `Pending`.

A preservação do último resultado permite manter o contexto histórico sem
confundir configuração com disponibilidade atual.

---

## Dashboard

Endpoint:

```http
GET /dashboard/summary
```

Requer autenticação JWT.

O dashboard considera apenas os monitores pertencentes ao usuário
autenticado.

### Resposta

```json
{
  "total_monitors": 3,
  "active_monitors": 2,
  "paused_monitors": 1,
  "up_monitors": 1,
  "down_monitors": 1,
  "pending_monitors": 0,
  "checks_last_24h": 120,
  "average_response_time_ms_24h": 84.5
}
```

### Campos

| Campo | Descrição |
| --- | --- |
| `total_monitors` | Total de monitores do usuário |
| `active_monitors` | Monitores com monitoramento ativo |
| `paused_monitors` | Monitores pausados |
| `up_monitors` | Monitores ativos cujo último check é UP |
| `down_monitors` | Monitores ativos cujo último check é DOWN |
| `pending_monitors` | Monitores ativos sem checks |
| `checks_last_24h` | Checks do usuário nas últimas 24 horas |
| `average_response_time_ms_24h` | Média dos response times disponíveis nas últimas 24 horas |

O histórico das últimas 24 horas pode incluir checks pertencentes a monitores
que atualmente estão pausados, pois esses checks continuam sendo registros
históricos válidos.

---

## Histórico de checks

Endpoint:

```http
GET /monitors/{monitor_id}/checks
```

Parâmetros:

```text
limit=50
offset=0
```

Exemplo:

```http
GET /monitors/UUID/checks?limit=50&offset=0
```

### Limites

- `limit` padrão: 50;
- `limit` máximo: 100;
- `offset` mínimo: 0.

O histórico é ordenado do check mais recente para o mais antigo.

### Resposta

```json
{
  "items": [
    {
      "status": "UP",
      "http_status_code": 200,
      "response_time_ms": 92,
      "error_type": null,
      "error_message": null,
      "checked_at": "2026-10-04T23:18:56Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

A paginação atual utiliza `limit` e `offset`.

Como novos checks podem ser inseridos enquanto o usuário navega pelas páginas,
a posição dos registros pode mudar entre requisições. Uma futura evolução
pode substituir esse modelo por paginação baseada em cursor utilizando
`checked_at` e um identificador estável.

---

## Estatísticas do monitor

Endpoint:

```http
GET /monitors/{monitor_id}/stats
```

Exemplo:

```http
GET /monitors/UUID/stats?window_hours=24
```

### Janela

`window_hours` aceita valores entre:

```text
1 e 168 horas
```

O valor utilizado pelo frontend é:

```text
24 horas
```

### Resposta

```json
{
  "monitor_id": "UUID",
  "window_hours": 24,
  "total_checks": 100,
  "successful_checks": 99,
  "failed_checks": 1,
  "uptime_percentage": 99.0,
  "average_response_time_ms": 87.4,
  "minimum_response_time_ms": 54,
  "maximum_response_time_ms": 213
}
```

---

## Cálculo de uptime

O uptime utiliza:

```text
successful_checks
────────────────── × 100
   total_checks
```

Equivalentemente:

```text
UP checks / total checks × 100
```

Exemplo:

```text
99 checks UP
1 check DOWN

99 / 100 × 100 = 99%
```

Quando a janela não possui checks:

```json
"uptime_percentage": null
```

Isso diferencia corretamente "nenhum dado disponível" de um uptime de `0%`.

---

## Response time

As estatísticas calculadas são:

- média;
- mínimo;
- máximo.

Somente checks que possuem `response_time_ms` participam desses cálculos.

Checks sem response time não são convertidos artificialmente para zero.

Quando nenhum check da janela possui response time:

```json
{
  "average_response_time_ms": null,
  "minimum_response_time_ms": null,
  "maximum_response_time_ms": null
}
```

---

## Autorização

Todos os endpoints desta versão utilizam o usuário autenticado.

Um usuário somente pode acessar:

- seu próprio dashboard;
- o histórico de seus monitores;
- as estatísticas de seus monitores.

Um `monitor_id` pertencente a outro usuário não expõe informações do recurso.

Essa regra mantém o isolamento dos dados entre usuários.

---

## Cache

Os endpoints de dashboard, histórico e estatísticas retornam:

```http
Cache-Control: no-store
```

Os dados representam estado operacional recente e não devem ser reutilizados
pelo navegador como uma resposta armazenada.

---

## Frontend

A v0.5 adiciona três componentes principais:

```text
DashboardSummary.tsx
MonitorDetails.tsx
ResponseTimeChart.tsx
```

### DashboardSummary

Exibe:

- total de monitores;
- Operational;
- Down;
- Pending;
- Paused;
- checks nas últimas 24 horas;
- response time médio nas últimas 24 horas.

### MonitorDetails

Exibe:

- nome e URL;
- Active/Paused;
- UP/DOWN/Pending;
- uptime;
- média de response time;
- response time mínimo;
- response time máximo;
- quantidade de checks;
- checks bem-sucedidos;
- checks com falha;
- gráfico;
- histórico recente.

### ResponseTimeChart

O gráfico utiliza Recharts.

O backend retorna o histórico do mais recente para o mais antigo. Para a
representação temporal do gráfico, o frontend reorganiza os pontos em ordem
cronológica.

Checks sem `response_time_ms` não são incluídos na série.

---

## Atualização periódica

Dashboard e dados operacionais são atualizados periodicamente pelo frontend.

A página de detalhes consulta novamente:

```http
GET /monitors/{id}/stats?window_hours=24
GET /monitors/{id}/checks?limit=50&offset=0
```

O intervalo atual é de aproximadamente 30 segundos enquanto a página está
visível.

Quando a aba do navegador está oculta, requisições desnecessárias são
evitadas.

---

## Validação

A v0.5 foi validada em backend, frontend, banco e ambiente Docker.

### Backend

```bash
cd backend
source .venv/bin/activate

python3 -m pytest -q
python3 -m compileall app
```

Resultado validado durante o fechamento da versão:

```text
195 passed
```

Existe um warning de depreciação proveniente de `Starlette TestClient` /
`AnyIO`, sem falha funcional nos testes.

### Frontend

```bash
cd frontend

npm run lint
npm run build
```

Validação:

```text
oxlint: 0 warnings, 0 errors
Vite production build: successful
```

O build atual inclui Recharts e pode emitir um aviso de chunk JavaScript
superior a 500 kB. Esse aviso não impede o build e pode ser tratado
posteriormente com code splitting/lazy loading.

### Alembic

A validação deve ser executada no ambiente Docker, onde o hostname interno do
PostgreSQL é resolvido:

```bash
docker compose exec api alembic current
docker compose exec api alembic heads
docker compose exec api alembic check
```

Resultado validado:

```text
b7c4e920d631 (head)
No new upgrade operations detected.
```

Isso confirma que o banco está alinhado com o head das migrations e que a
v0.5 não introduziu alterações de schema pendentes.

### Docker

Serviços validados:

```text
statuswatch-api
statuswatch-db
statuswatch-redis
statuswatch-web
statuswatch-worker
```

API, PostgreSQL e Redis possuem health checks e foram validados como
saudáveis durante o fechamento da versão.

---

## Testes manuais

O fluxo de frontend foi validado manualmente:

```text
Login
  ↓
Dashboard
  ↓
Lista de monitores
  ↓
View details
  ├── Performance 24h
  ├── Response time chart
  └── Check history
  ↓
Back to monitors
```

Também foram validados:

- monitor sem checks;
- monitor UP;
- monitor DOWN;
- monitor pausado;
- preservação do último resultado ao pausar;
- atualização periódica;
- histórico newest-first;
- estatísticas de 24 horas;
- validações dos parâmetros da API;
- isolamento por usuário.

---

## Arquivos principais da v0.5

### Backend

```text
backend/app/api/routes/dashboard.py
backend/app/api/routes/monitor_history.py
backend/app/schemas/dashboard.py
backend/app/services/dashboard.py
backend/tests/test_dashboard.py
backend/tests/test_monitor_history.py
```

### Frontend

```text
frontend/src/DashboardSummary.tsx
frontend/src/MonitorDetails.tsx
frontend/src/ResponseTimeChart.tsx
frontend/src/Monitors.tsx
frontend/src/api.ts
frontend/src/App.css
```

---

## Limitações conhecidas

### Paginação

O histórico utiliza paginação baseada em offset. Inserções concorrentes podem
alterar a posição dos registros entre páginas.

Uma evolução futura poderá utilizar cursor baseado em:

```text
checked_at + id
```

### Bundle frontend

A inclusão do Recharts aumentou o bundle JavaScript principal.

Uma evolução futura poderá carregar a tela de detalhes e o gráfico sob demanda
utilizando code splitting.

### Incidentes

A v0.5 trabalha diretamente com resultados de checks.

Ela ainda não implementa agrupamento de falhas consecutivas em incidentes.

Essa funcionalidade pertence à v0.6.

### Notificações

Alertas e destinos de notificação ainda não fazem parte desta versão.

Essa funcionalidade está planejada para a v0.7.

---

## Próxima etapa

A próxima milestone é:

```text
v0.6 — Incidents
```

Objetivo inicial:

- detectar sequências de falhas;
- abrir incidente após o threshold definido;
- manter somente um incidente aberto por monitor;
- resolver o incidente quando o serviço voltar a responder com `UP`;
- preservar timestamps de início e resolução;
- disponibilizar incidentes através da API e do frontend.

Notificações permanecem fora do escopo da v0.6 e serão tratadas
separadamente na v0.7.

## Integração posterior

A v0.6 adiciona `open_incidents` ao resumo e histórico de incidentes nos detalhes,
sem alterar uptime, stats ou paginação de checks. OPEN não é derivado de DOWN.
Veja [incidents.md](incidents.md) e [notifications.md](notifications.md).
