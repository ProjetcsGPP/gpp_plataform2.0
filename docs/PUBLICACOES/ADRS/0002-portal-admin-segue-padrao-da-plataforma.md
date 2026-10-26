# ADR-0002 — `PORTAL_ADMIN` segue o padrão da plataforma

**Status:** aceito  
**Data:** 2026-10-23  
**Matriz:** `PUB-010`

## Contexto

As camadas compartilhadas de IAM da plataforma tratam `PORTAL_ADMIN` e
`superuser` como administradores globais. `request.is_portal_admin` permite
acesso entre aplicações e o serviço compartilhado de autorização dispensa a
permissão técnica específica da aplicação.

## Decisão

`PUBLICACOES` manterá esse comportamento, sem criar uma exceção local ou um
segundo mecanismo de autorização. `PORTAL_ADMIN` e `superuser` terão o mesmo
acesso administrativo global usado nas demais aplicações, sem necessidade de
vínculo ou permissão específica em `PUBLICACOES`.

O administrador tem acesso a tudo, mas não ignora regras da aplicação. Continua
sujeito ao workflow, imutabilidade de versões publicadas, validações,
justificativas, concorrência e auditoria.

## Matriz de autorização

| Ator | Acesso à aplicação | Ação editorial | Regras de domínio |
|---|---|---|---|
| `GESTOR_PUBLICACOES` com permissão | Sim | Conforme permissão técnica | Obrigatórias |
| `GESTOR_PUBLICACOES` sem permissão | Sim, conforme capability | Negada | Obrigatórias |
| `PORTAL_ADMIN` ou `superuser` | Global | Permitida pela autorização compartilhada | Obrigatórias |
| Usuário comum sem vínculo | Negado | Negada | Obrigatórias |
| Consumidor de API | Somente contrato M2M e escopos | Não se aplica | Obrigatórias |

## Consequências e controles

- o frontend não implementará bypass próprio nem condicionais por nome de role;
- o backend utilizará middleware, contexto e permissões compartilhados;
- toda ação editorial administrativa será auditada com o ator real;
- testes cobrirão administrador, gestor autorizado e usuário comum sem acesso;
- testes também impedirão que o administrador viole invariantes do domínio.

## Critério de aceite

O administrador acessa e executa ações autorizáveis sem vínculo específico com
`PUBLICACOES`; o usuário comum sem permissão recebe negação; ambos permanecem
sujeitos às mesmas invariantes transacionais e de auditoria.
