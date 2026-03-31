# Autenticação e troca de contexto no GPP

## Objetivo

Este documento descreve como o frontend deve integrar com o backend Django do GPP usando autenticação por sessão e troca de contexto por aplicação.

## Regras do backend

- O backend autentica exclusivamente por sessão Django.
- O cookie de sessão é `gpp_session`.
- A revogação real da sessão é controlada por `accounts_session`.
- O backend injeta `request.user`, `request.application`, `request.user_roles` e `request.is_portal_admin` em cada request.

## Fluxos suportados

### 1. Login direto em uma aplicação

Usuário informa credenciais e o `app_context` da aplicação desejada.
Se ele tiver role nessa aplicação, a sessão é criada já contextualizada.

### 2. Login no Portal

`PORTAL` é um contexto especial.
Somente usuários com `PORTAL_ADMIN` ou superuser conseguem entrar nele.

### 3. Troca de contexto depois do login

Se o usuário entrar no Portal e depois escolher outra aplicação permitida, o frontend deve chamar o endpoint de switch de aplicação.
O cookie permanece o mesmo, mas o `app_context` da sessão muda e o backend passa a carregar as roles daquela aplicação.

## O que muda no switch de contexto

- O cookie `gpp_session` não muda.
- A sessão Django continua autenticada.
- O backend troca o `app_context` armazenado na sessão.
- Uma nova `AccountsSession` é criada para o novo contexto.
- As próximas chamadas passam a obedecer às permissões da aplicação escolhida.

## Situações suportadas

- Login direto em `ACOES_PNGI`.
- Login direto em `CARGA_ORG_LOT`.
- Login no `PORTAL` por `PORTAL_ADMIN`.
- Entrar no Portal e depois alternar para outra aplicação autorizada.
- Alternar entre aplicações permitidas sem relogar.

## Situações não suportadas

- Login no `PORTAL` por usuário sem `PORTAL_ADMIN`.
- Trocar para uma aplicação na qual o usuário não possui role.
- Acessar uma aplicação sem autenticação válida.
- Tentar tratar `gpp_session` como JWT ou token Bearer.

## Padrão de consumo no frontend

- Sempre enviar `credentials: 'include'` nas requisições.
- Sempre usar o mesmo backend base URL.
- Após login ou switch, chamar um endpoint de estado, como `me`, para atualizar o contexto da interface.
- Exibir somente as aplicações retornadas pelo backend para o usuário autenticado.

## Fluxo recomendado

1. Buscar as aplicações públicas para preencher o seletor de login.
2. Fazer login com `username`, `password` e `app_context`.
3. Ler o usuário autenticado com `me`.
4. Se for Portal Admin, listar apps disponíveis pós-login.
5. Ao trocar de app, chamar switch de contexto.
6. Recarregar estado e permissões após o switch.
