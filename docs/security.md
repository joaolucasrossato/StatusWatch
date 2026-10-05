# Segurança e dependências — revisão v1.0

Revisão em 05/10/2026. JWT exige secret com pelo menos 32 caracteres e claims
exp/sub/type; algoritmos permitidos HS256/384/512. Senhas usam Argon2.
Endpoints protegidos consultam current_user e ownership; recursos alheios dão 404.
Erros 422 omitem inputs sensíveis, falhas operacionais do banco retornam 503
genérico e o frontend não exibe detalhes de respostas 5xx.

Checks e webhooks validam DNS/IP públicos e fixam o IP da conexão, mantendo Host,
SNI e TLS. Checks revalidam cada redirect; webhooks recusam redirects. Cookies
são removidos, proxies do ambiente ignorados e nenhum JWT é enviado ao destino.
URLs de webhook expõem somente a origem; editar sem novo destino preserva o
valor existente. DNS de criação/edição ocorre fora da transação de banco.

Destinos ficam em texto claro no PostgreSQL: restrinja acesso ao banco/backups e
use criptografia de volume/backup do provedor. Criptografia por aplicação exige
KMS/gestão e rotação de chaves, versionamento de ciphertext e migração; não foi
introduzida criptografia caseira. O serviço notification_channels centraliza o
acesso para essa evolução. URLs dos monitores são visíveis ao proprietário e
entram no payload das notificações; evite colocar secrets nelas.

## Egress e publicação

Aplicação SSRF não substitui firewall. Restrinja API/worker a DNS autorizado,
HTTP/HTTPS públicos necessários, SMTP configurado e PostgreSQL/Redis internos.
Bloqueie metadata, redes privadas e link-local também na rede; permita banco e
Redis apenas nos destinos internos específicos. Ajuste portas externas à política
do ambiente. A v1 não configura firewall específico de provedor.

Produção publica somente Nginx em loopback 8080, com proxy /api. API/banco/Redis
não publicam portas. Termine HTTPS no gateway de produção; preserve cabeçalhos
nosniff, DENY e no-referrer. Não há wildcard CORS, SQL construído com inputs ou
secrets no bundle. .env/.env.production são ignorados e excluídos das imagens.
A documentação histórica v0.3 registra secret exposto no histórico Git: a rotação
fora do laboratório continua necessária; esta revisão não reescreve o histórico.
Não há rate limiting/login throttling na aplicação; limite abuso no gateway.

## Auditoria de dependências

`npm audit`: zero vulnerabilidades. `pip-audit` sobre a .venv: 16 registros,
8 advisories distintos em 2 pacotes (o feed contém duplicatas). Dependências
diretas antes sem pin foram fixadas às versões já utilizadas e testadas.

| Pacote | Advisory | Versão corrigida informada |
| --- | --- | --- |
| pytest 8.3.5 | [GHSA-6w46-j5rx-g56g](https://github.com/advisories/GHSA-6w46-j5rx-g56g) | 9.0.3 |
| starlette 0.46.2 | [GHSA-2c2j-9gv5-cj73](https://github.com/advisories/GHSA-2c2j-9gv5-cj73) | 0.47.2 |
| starlette 0.46.2 | [GHSA-7f5h-v6xp-fcq8](https://github.com/advisories/GHSA-7f5h-v6xp-fcq8) | 0.49.1 |
| starlette 0.46.2 | [GHSA-86qp-5c8j-p5mr](https://github.com/advisories/GHSA-86qp-5c8j-p5mr) | 1.0.1 |
| starlette 0.46.2 | [GHSA-wqp7-x3pw-xc5r](https://github.com/advisories/GHSA-wqp7-x3pw-xc5r) | 1.1.0 |
| starlette 0.46.2 | [GHSA-x746-7m8f-x49c](https://github.com/advisories/GHSA-x746-7m8f-x49c) | 1.1.0 |
| starlette 0.46.2 | [GHSA-82w8-qh3p-5jfq](https://github.com/advisories/GHSA-82w8-qh3p-5jfq) | 1.3.1 |
| starlette 0.46.2 | [GHSA-jp82-jpqv-5vv3](https://github.com/advisories/GHSA-jp82-jpqv-5vv3) | 1.3.0 |

Starlette: as superfícies reportadas são formulários/uploads, FileResponse/StaticFiles,
HTTPEndpoint com métodos implícitos e decisões de segurança baseadas em request.url.
A API atual usa JSON, endpoints FastAPI com métodos explícitos e ownership no
banco; arquivos estáticos são servidos pelo Nginx Linux. Não foi identificado uso
dessas superfícies vulneráveis no código atual. Isso não equivale a um scan sem
vulnerabilidades. FastAPI 0.115.12 restringe Starlette a <0.47: corrigir todos os
advisories exige upgrade coordenado de FastAPI e Starlette (incluindo major 1.x),
adiado conforme o escopo de evitar upgrades disruptivos.

pytest é somente desenvolvimento e precisa de major 9.0.3 para o advisory de
diretórios temporários locais. Execute testes como usuário sem privilégios em
host confiável; planeje esse upgrade separadamente. Não se deve executar a suíte
como root em host compartilhado com usuários não confiáveis.

Limites adicionais: uma réplica do scheduler, sem fila distribuída; dependências
transitivas e imagens-base ainda dependem do registry (não há lock completo por
hash/digest); validar novamente a auditoria antes de publicar a release.
