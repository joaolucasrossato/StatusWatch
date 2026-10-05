# Incidents — v0.6.0

Incidentes são geridos pelo engine, não por ações manuais. O terceiro DOWN
consecutivo abre um OPEN. `started_at` registra o primeiro DOWN e `opened_at`
o terceiro. DOWN adicionais mantêm o mesmo incidente. O primeiro UP resolve
como RESOLVED, com `resolved_at` igual ao timestamp desse check. UP antes do
terceiro DOWN quebra a sequência. Uma nova abertura exige três novas falhas.
Active/Paused, UP/DOWN e OPEN/RESOLVED são conceitos independentes.

Check e transição são persistidos na mesma transação. O índice parcial
PostgreSQL `uq_incidents_open_monitor` garante no máximo um OPEN por monitor;
`ix_incidents_monitor_id_started_at`, `ck_incidents_status` e
`ck_incidents_resolution` preservam consulta e integridade.

## API

- `GET /incidents`: histórico de todos os monitores do usuário.
- `GET /incidents/{incident_id}`: detalhe.
- `GET /monitors/{monitor_id}/incidents`: histórico de um monitor.

Listagens aceitam `status=OPEN|RESOLVED`, `limit` (1–100, padrão 50) e
`offset` (>=0). Retornam `items`, `total`, `limit`, `offset`, ordenados por
started_at/id decrescentes. JWT obrigatório; recursos alheios retornam 404,
parâmetros inválidos 422. Respostas usam `Cache-Control: no-store`.
Não existem POST/PATCH de incidentes.

## Frontend

Navegação React por estado entre Monitors e Incidents, sem router adicional.
A lista global mostra nomes locais dos monitores, status e timestamps,
com filtros All/OPEN/RESOLVED, Previous/Next e contagem de registros.
Alterar filtro reinicia offset. Há estados loading, erro, vazio e Reload.
O card Open incidents usa exclusivamente `summary.open_incidents`.
Nos detalhes, incidentes paginados compartilham o carregamento e o timer de
stats/history. O status operacional usa o check mais recente carregado.
Polling de 30 segundos é suspenso enquanto a página está oculta; requests
são abortadas ao desmontar. Uma requisição já iniciada pode terminar ao ocultar.

## Limites

Não há reconhecimento manual, edição, retenção automática, severidades ou
página pública. O worker de monitoramento continua com uma réplica.
Notificações são implementadas na etapa v0.7, documentada separadamente.
