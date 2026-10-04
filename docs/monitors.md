# Monitor Management — v0.3.0

Um monitor guarda **quais serviços o usuário deseja monitorar**. Nenhuma requisição é enviada à URL cadastrada. HTTP checks are not executed yet. Monitoring execution will be introduced in v0.4.

## Modelo e relacionamento

`User.monitors` ↔ `Monitor.user`: relação 1:N com `back_populates`, cascade ORM `all, delete-orphan`, `passive_deletes=True` e FK `ON DELETE CASCADE`.

| Campo | Tipo / regra |
| --- | --- |
| id | UUID, PK, gerado pela aplicação |
| user_id | UUID obrigatório, FK users.id, índice ix_monitors_user_id |
| name | String(120), trim, 1–120 caracteres, não aceita espaços apenas |
| url | String(2083), HttpUrl Pydantic: somente http/https com host válido |
| method | String(10), somente GET; default GET na API |
| interval_seconds | Inteiro, 30/60/300/600; default 60 na API |
| timeout_seconds | Inteiro estrito, 1–30; default 10 na API |
| is_active | Boolean obrigatório, default true |
| created_at | Timestamp com timezone, server default now() |
| updated_at | Timestamp com timezone, server default now(), onupdate=now() no ORM |

Constraints no banco garantem interval e timeout positivos. A API valida as opções disponíveis nesta versão. URLs são normalizadas pelo Pydantic (por exemplo, host sem caminho ganha `/`). Somente o índice de ownership é necessário nesta versão.

## Autenticação e isolamento

Todas as rotas exigem `Authorization: Bearer <token>` obtido em `/auth/login`. A dependency existente verifica o JWT e obtém `User` pelo UUID em `sub`. `user_id` vem exclusivamente desse usuário. Campos extras são rejeitados com 422; `id`, `user_id` e timestamps não podem ser escolhidos ou editados.

GET individual, PATCH e DELETE compartilham uma consulta parametrizada filtrada por **monitor.id E monitor.user_id**. Um recurso inexistente e um recurso alheio retornam o mesmo `404 {"detail":"Monitor not found"}`. Listagem retorna exclusivamente monitores do usuário, ordenados por `created_at DESC, id DESC` (desempate determinístico), sem paginação.

| Método / path | Resultado |
| --- | --- |
| POST /monitors | 201 com MonitorResponse |
| GET /monitors | 200 com array (possivelmente vazio) |
| GET /monitors/{monitor_id} | 200 com MonitorResponse |
| PATCH /monitors/{monitor_id} | 200 com MonitorResponse atualizado |
| DELETE /monitors/{monitor_id} | 204 sem corpo |

Códigos comuns: 401 para token ausente/inválido/expirado ou usuário removido; 403 para usuário inativo; 404 para monitor ausente/alheio; 422 para UUID ou payload inválido.

## Exemplo de criação

```http
POST /monitors
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "StatusWatch API",
  "url": "https://example.com/health",
  "method": "GET",
  "interval_seconds": 60,
  "timeout_seconds": 10,
  "is_active": true
}
```

Resposta ilustrativa (UUIDs fictícios):

```json
{
  "id": "00000000-0000-4000-8000-000000000001",
  "user_id": "00000000-0000-4000-8000-000000000002",
  "name": "StatusWatch API",
  "url": "https://example.com/health",
  "method": "GET",
  "interval_seconds": 60,
  "timeout_seconds": 10,
  "is_active": true,
  "created_at": "2026-10-04T12:00:00Z",
  "updated_at": "2026-10-04T12:00:00Z"
}
```

PATCH `/monitors/{id}` com `{"is_active":false}` pausa a configuração, preservando os demais campos. `exclude_unset=True` distingue campos omitidos. Todos os campos enviados são revalidados; `null` explícito é inválido. `{}` é aceito e não altera o monitor. Nomes são aparados antes de validar comprimento. Métodos POST/PUT/PATCH/DELETE, intervalos fora da lista e esquemas ftp/file/javascript/data são rejeitados.

## Migration

Revision `9d2f3a7c8b10`, down_revision `4bffcd0e1da1`. A migration existente de users não foi alterada. `upgrade head` cria monitors/índice; `downgrade -1` remove somente monitors/índice, preservando users. O registry importa ambos os models explicitamente. A atualização de updated_at segue o padrão ORM de User; não é um trigger para SQL externo.

## Interface e limites

Cadastro/login, lista, formulário de criação/edição, ação Pause/Activate e confirmação de exclusão. Token apenas em memória, enviado em Authorization. A sessão precisa de novo login ao recarregar a página ou expirar. Active/Paused é somente configuração: **não significa UP/DOWN**. O painel de saúde da própria plataforma permanece separado.

Sem checks HTTP, scheduler, filas, histórico, uptime, latência, incidentes, alertas ou planos. Não há paginação nesta versão.

## SSRF na v0.4

Aceitar HTTP/HTTPS **não é proteção SSRF**. Antes de implementar execução, o engine precisará de uma política completa para endereços privados/reservados, resolução DNS e rebinding, redirects e validação de cada destino, além de controles de rede. Esta versão não tenta implementar proteção parcial: nenhuma URL de monitor é acessada.
