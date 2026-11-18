# Autenticação Next.js — contrato do backend

**Última revisão:** 2026-10-23
**Matriz compartilhada:** `PUB-008` e `PUB-015`

## Contrato atual

- autenticação humana usa sessão Django, nunca JWT ou Bearer token;
- cada aplicação possui cookie `gpp_session_<APP_CONTEXT>` independente;
- cookies de sessão são `HttpOnly`, `SameSite=Lax` e `Secure=True` em produção;
- mutações autenticadas e login exigem CSRF;
- sessão somente é aceita quando não revogada, não expirada, pertence ao mesmo
  contexto indicado pelo cookie e o usuário continua ativo;
- login tem throttle dedicado por IP, configurado por
  `LOGIN_THROTTLE_RATE`;
- `X-Forwarded-For` só participa do throttle quando `DRF_NUM_PROXIES` contém a
  quantidade exata de proxies confiáveis;
- falha de credencial não revela se username, e-mail ou conta existem.

## Login

1. Chamar `GET /api/accounts/auth/csrf/` com credenciais habilitadas.
2. Ler o cookie `csrftoken`.
3. Chamar `POST /api/accounts/login/`, enviando o cookie e o header
   `X-CSRFToken` com o mesmo valor.

Payload:

```json
{
  "identifier": "usuario-ou-email",
  "password": "senha",
  "app_context": "PORTAL"
}
```

`username` permanece temporariamente aceito como alias para clientes antigos.
Novas integrações devem usar exclusivamente `identifier`.

Em sucesso, a resposta define `gpp_session_PORTAL` ou o cookie correspondente
à aplicação. O frontend não lê esse cookie; o browser o envia com
`credentials: include` ou `withCredentials: true`.

O endpoint `/api/accounts/auth/resolve-user/` foi descontinuado. Clientes não
devem tentar resolver o identificador antes do login.

## Requisições posteriores

- `GET`, `HEAD` e `OPTIONS` não exigem header CSRF.
- `POST`, `PUT`, `PATCH` e `DELETE` autenticados enviam `X-CSRFToken`.
- após o login, o token CSRF pode ser rotacionado; o cliente deve reler o
  cookie antes de cada mutação, como já faz o interceptor compartilhado.
- resposta `401` significa sessão ausente/inválida no contrato autenticado;
  chamadas públicas devem possuir tratamento próprio no frontend.

## Troca e isolamento de aplicações

O endpoint autenticado `POST /api/accounts/switch-app/` cria a sessão/cookie da
aplicação de destino após validar acesso. O cookie de uma aplicação não pode ser
reaproveitado com registro de contexto divergente. Logout seletivo revoga apenas
a sessão indicada e exige `X-CSRFToken`, inclusive quando a sessão a limpar já
estiver inválida.

## Referências

- [Contrato completo da API](./API_CONTRACT.md)
- [IAM e autenticação](./IAM_AUTENTICACAO.md)
- [Matriz compartilhada](./SHARED/PUBLICACOES_INTEGRATION_MATRIX.md)
