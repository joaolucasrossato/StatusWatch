# Retenção — v1.0

O worker executa cleanup no início e a cada hora, em tarefa independente do
scheduler e das notificações. `CHECK_RETENTION_DAYS` e
`NOTIFICATION_RETENTION_DAYS` aceitam inteiros de 1 a 3650 (padrão 30).
O cutoff é UTC; somente registros estritamente anteriores são removidos.

- `monitor_checks`: usa `checked_at`.
- `notification_deliveries`: usa `created_at`, somente SENT/FAILED.
- PENDING/PROCESSING ficam disponíveis para retry/recuperação, mesmo antigos.
- Incidentes não são removidos automaticamente. Excluir monitor/canal continua
  aplicando as cascatas existentes.

A transação de cleanup contém apenas DELETEs e commit; falhas fazem rollback,
registram `cleanup_failed` sem dados sensíveis e aguardam o próximo ciclo horário.
`cleanup_completed` informa contagens. Há índices por data na migration
`a81d4e29b607`; nenhuma migration anterior foi alterada.

Após longa pausa ou indisponibilidade maior que a retenção, o último check e a
sequência de falhas podem expirar. O monitor passa a não ter histórico disponível;
ao reativar, recebe check imediato e uma nova sequência de três DOWN é necessária
se não houver incidente aberto. Incidentes abertos existentes permanecem e o
primeiro UP os resolve. Stats refletem apenas os checks retidos: configure pelo
menos 7 dias para manter toda a janela máxima de 168 horas.

A retenção não é arquivo permanente nem substitui backup. Entregas antigas
removidas perdem seu histórico e sua chave de deduplicação local; não existe replay
retroativo nesta versão. O receptor deve manter sua própria deduplicação conforme
sua política. Bancos muito grandes podem precisar de cleanup em lotes e VACUUM
ajustado; o timeout de consultas do worker limita a operação e falhas são logadas.
