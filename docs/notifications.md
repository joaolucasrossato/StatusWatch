# Notifications — v0.7.0

> Documento da etapa histórica indicada no título. Para o estado consolidado,
> consulte o [README](../README.md), a [retenção](retention.md),
> a [segurança](security.md) e a [validação v1.0](validation-v1.0.md).

## Arquitetura e lifecycle

Notificações são consequência de transições de incidentes, nunca de cada DOWN.
O terceiro DOWN abre o incidente e enfileira `INCIDENT_OPENED`; o primeiro UP
resolve e enfileira `INCIDENT_RESOLVED`. DOWN/UP adicionais não duplicam eventos.
Somente canais ativos e habilitados para o evento no momento da transição
recebem uma entrega. Canais criados depois não recebem eventos retroativos.

`persist_check` persiste check, incidente e outbox na mesma transação.
`enqueue_transition` apenas faz flush; qualquer rollback desfaz os três.
A constraint `uq_notification_delivery_transition` torna
(incident_id, channel_id, event_type) único. O payload JSON captura nome/URL do
monitor e timestamps/status na transição; um OPENED continua descrevendo OPEN
mesmo que o incidente seja resolvido antes do envio.

Uma tarefa independente no processo worker consome até 20 entregas por ciclo.
O scheduler HTTP mantém sua execução independente. Não há Celery, fila Redis
adicional, nem HTTP/SMTP dentro da transação de persistência dos checks.
O worker fecha a transação do claim antes de enviar e abre outra para registrar
o resultado. Falhas de envio não removem a outbox e não param o monitoring.

## Estados, tentativas e recuperação

- PENDING: aguardando a próxima tentativa.
- PROCESSING: reservada com token exclusivo e lease de 5 minutos.
- SENT: transporte aceitou o envio; `sent_at` é preenchido.
- FAILED: falha definitiva, canal desabilitado ou lease final expirado.

No máximo 3 tentativas: a primeira quando o evento está disponível; depois
1 minuto e 5 minutos após cada falha. `attempt_count` incrementa no claim e
`next_attempt_at` persiste a espera. Um crash não reinicia os contadores.
Lease expirado pode ser retomado; tokens impedem que um processamento antigo
sobrescreva o resultado do novo. PostgreSQL usa `FOR UPDATE SKIP LOCKED` e
atualização condicional. O monitoring ainda deve executar com uma réplica.

A outbox evita duplicação lógica, mas a entrega externa é **at-least-once**:
um crash após o destinatário aceitar e antes de gravar SENT pode repetir o
envio. Webhooks incluem `Idempotency-Key` com o UUID da entrega; o receptor deve
deduplicar. Emails reutilizam Message-ID, sem garantia de deduplicação SMTP.
SENT indica aceitação SMTP/HTTP 2xx, não leitura nem entrega na caixa postal.
Não há replay manual, dead-letter UI, rate limit ou garantia de ordem entre
OPENED/RESOLVED quando existem retries.

## Canais e segurança

EMAIL e WEBHOOK pertencem a um usuário e obrigatoriamente a um monitor dele.
O usuário vem do JWT. Monitor e tipo são imutáveis após criar o canal.
PATCH permite destino, is_active, notify_on_open e notify_on_resolved.
Ambos os eventos podem ser desmarcados; nesse caso não se geram novas entregas.

Desabilitar um canal impede novos eventos e cancela entregas ainda não
reservadas como FAILED no próximo processamento. Uma entrega já reservada pode
terminar. Alterar o destino afeta tentativas futuras, pois o worker lê o canal
no claim. Excluir canal elimina suas entregas por cascade; excluir monitor
elimina canais, incidentes e entregas. A UI pede confirmação da exclusão.

Webhooks aceitam HTTP/HTTPS públicos; **prefira HTTPS**. Credenciais embutidas,
fragmentos e caracteres de controle são recusados. A API resolve DNS com prazo
de 10 segundos. O worker revalida a cada envio todos os IPs retornados e conecta
ao IP aprovado, preservando Host/SNI e verificação TLS. Bloqueia localhost,
loopback IPv4/IPv6, redes privadas, link-local, metadata e DNS para endereços
não públicos. Redirects são tratados como falha; nenhum é seguido.
O cliente ignora proxies do ambiente, remove cookies e não envia Authorization.
O prazo HTTP total é de 10 segundos; resposta externa não é persistida/lida
integralmente. As proteções da aplicação não substituem regras de egress.

A API retorna somente a origem de webhooks seguida de `/…`, ocultando também
paths que podem conter tokens. No formulário de edição, deixe o destino vazio
para preservá-lo; informe uma URL completa para substituí-lo. Não reenvie o
valor mascarado. O banco guarda o destino necessário para envio; proteja banco
e backups. Não há criptografia adicional de campos nesta versão.
Payloads não são expostos pela API de entregas. Erros de validação de canais
não devolvem o input original. Logs contêm somente IDs e códigos fixos.

## Email e configuração

O Compose de desenvolvimento e produção passa as seguintes variáveis à API e
ao worker. Os fragmentos históricos em `backend/compose*.yaml` não são os
arquivos de execução; use os Compose da raiz.

| Variável | Padrão / uso |
| --- | --- |
| SMTP_HOST | vazio; servidor SMTP |
| SMTP_PORT | 587 |
| SMTP_USERNAME | vazio; autenticação opcional |
| SMTP_PASSWORD | vazio; secret fornecido pelo ambiente |
| SMTP_FROM | vazio; remetente |
| SMTP_USE_TLS | true; STARTTLS com certificado validado |

Configure credenciais no ambiente, nunca no código. Recrie API/worker depois
de alterar variáveis. STARTTLS é o modo TLS suportado; TLS implícito na porta
465 não está implementado. `SMTP_USE_TLS=false` destina-se a transportes locais
controlados. Timeout SMTP é de 10 segundos por operação de socket.

Se HOST ou FROM estiver vazio, canais EMAIL continuam configuráveis e API e
worker iniciam normalmente. A entrega registra `smtp_not_configured`, tenta
novamente com backoff e termina FAILED após três tentativas. Não há envio real
nos testes automatizados.

O email contém StatusWatch, evento, nome/URL do monitor, started_at, opened_at e
resolved_at quando aplicável. O webhook POST JSON contém `event`, `incident`
(id, status e timestamps) e `monitor` (id, name, url). Esses dados vão somente
ao destino configurado pelo proprietário; não são incluídos em logs.

## API

Todas as rotas exigem autenticação, aplicam ownership e usam `no-store` nas
respostas da implementação de notificações. Recurso alheio/inexistente: 404;
parâmetro inválido: 422; credenciais ausentes/expiradas: 401.

| Método | Endpoint | Resultado |
| --- | --- | --- |
| GET | /notification-channels | Lista dos canais próprios |
| POST | /notification-channels | Cria canal, 201 |
| PATCH | /notification-channels/{id} | Atualiza destino/flags |
| DELETE | /notification-channels/{id} | Exclui canal e histórico, 204 |
| GET | /monitors/{monitor_id}/notification-channels | Canais do monitor |
| GET | /notification-deliveries | Histórico próprio paginado |
| GET | /incidents/{incident_id}/notification-deliveries | Entregas do incidente |

POST recebe monitor_id, type, target, is_active (true), notify_on_open (true),
notify_on_resolved (true). Não aceita user_id. PATCH omite campos inalterados;
null é inválido. Canais retornam id, monitor_id, type, target (mascarado para
webhook), target_redacted, flags, created_at e updated_at.

Entregas aceitam limit (1–100, padrão 50), offset (>=0), status e event_type;
a listagem global também aceita monitor_id. Resposta: items/total/limit/offset,
ordenados por created_at/id decrescentes. Cada entrega inclui id, incident_id,
channel_id, event_type, status, attempt_count, last_error, created_at, sent_at e
next_attempt_at. Não há criação manual de entrega por API.

## Interface

Monitor details → Notifications abre configuração e histórico por monitor.
Há criação EMAIL/WEBHOOK, edição de destino e eventos, enable/disable e
exclusão confirmada. Histórico mostra evento, canal mascarado, estado,
tentativas e datas, com filtros e paginação real. Estados loading/erro/vazio,
recarregamento e expiração de sessão são tratados.
Polling de 30 segundos apenas com página visível, suspenso durante edição ou
mutação. Requests são abortadas na desmontagem. Detalhes do monitor suspendem
seu próprio carregamento enquanto Notifications está aberta.

## Migrations e testes

Nova revisão: `f7a10d92c630`, sucessora de `ec2cf41a52d5` (inalterada).
Cria notification_channels e notification_deliveries com constraints e índices.
Execute `docker compose run --rm api alembic upgrade head` antes de atualizar
os serviços. Valide current/heads/check após subir. Nunca faça downgrade para
teste no banco real: `backend/tests/validate_migrations.py` cria e remove um
banco PostgreSQL descartável e exige CREATEDB.

Backend: `python3 -m pytest -q` no ambiente virtual. Frontend: `npm test`,
`npm run lint`, `npm run build`. Testes cobrem canais, ownership, SSRF, eventos,
rollback, duplicação lógica, retries, leases, transportes mockados e interface.

## Troubleshooting

- `smtp_not_configured`: configure HOST/FROM e recrie o worker.
- `delivery_transport_error`: verifique rede, TLS e credenciais no ambiente;
  detalhes externos são omitidos para não vazar secrets.
- `webhook_destination_blocked`: destino/DNS não público; não desative SSRF.
- `webhook_http_error`: resposta não 2xx, inclusive redirects; use URL final.
- PROCESSING prolongado: confira worker; lease expirado será recuperado.
- PENDING: confira next_attempt_at, worker e conexão ao banco.
- FAILED: histórico terminal; esta versão não oferece replay manual.
- Nenhuma entrega: confira canal ativo, flags e se ocorreu uma nova transição
  depois de configurar o canal. DOWN isolado não é um incidente.

Logs `notification_delivery_sent` e `notification_delivery_failed` incluem
delivery_id, incident_id e monitor_id. `notification_delivery_cycle_failed`
indica falha no processamento/DB sem imprimir exceções potencialmente sensíveis.
