# Integração Next.js com a autenticação GPP

**Última revisão:** 2026-10-23
**Obrigação arquitetural:** reutilizar Axios, interceptors, SWR, `appContext` e
stores existentes; não criar cliente ou armazenamento de sessão paralelo.

## Fluxo obrigatório

1. Consultar `GET /api/accounts/auth/csrf/` com `withCredentials: true`.
2. Ler `csrftoken` do cookie.
3. Enviar `POST /api/accounts/login/` com `identifier`, `password` e
   `app_context`, incluindo `X-CSRFToken`.
4. Em sucesso, chamar `/api/accounts/me/` e hidratar estado, permissões,
   capabilities e menus pelos mecanismos compartilhados.
5. Relê-lo antes de cada mutação, pois o login pode rotacionar o token CSRF.

Exemplo conceitual usando o cliente compartilhado:

```ts
await api.get('/accounts/auth/csrf/')

await api.post('/accounts/login/', {
  identifier,
  password,
  app_context: appContext,
})
```

O interceptor existente deve obter `csrftoken` e enviar `X-CSRFToken`. Não
persista sessão, credencial ou token em `localStorage`, Zustand, SWR ou logs.

## Regras de compatibilidade

- remover qualquer chamada a `/accounts/auth/resolve-user/`;
- não converter e-mail em username no browser;
- apresentar a mesma mensagem para credencial inválida, independentemente do
  identificador;
- manter `username` apenas como alias transitório no backend, sem adotá-lo em
  código novo;
- não interpretar um `401` de endpoint público como sessão expirada;
- não enviar conteúdo de segredo para telemetria ou tratamento genérico de erro.

## Cookies e aplicações

Cada contexto usa `gpp_session_<APP>`, por exemplo:

| Contexto | Cookie |
|---|---|
| `PORTAL` | `gpp_session_PORTAL` |
| `ACOES_PNGI` | `gpp_session_ACOES_PNGI` |
| `CARGA_ORG_LOT` | `gpp_session_CARGA_ORG_LOT` |

O cookie é `HttpOnly` e não deve ser lido no JavaScript. O frontend usa o
`appContext` para selecionar o fluxo existente, mas a autorização final e a
lista de aplicações disponíveis continuam sob autoridade do backend.

## Testes mínimos do frontend

- bootstrap CSRF antes do login;
- login por username e e-mail usando `identifier`;
- ausência de chamada ao endpoint descontinuado;
- erro genérico de credencial;
- token relido após login;
- `403` por CSRF ausente/inválido;
- `429` de login sem loop automático;
- cookies e logout independentes por aplicação;
- `401` autenticado tratado separadamente de falha pública;
- nenhum segredo persistido em caches ou stores.

## Referências

- [Contrato do backend](./AUTH_NEXTJS_BACKEND.md)
- [Contrato completo da API](./API_CONTRACT.md)
- [Matriz compartilhada](./SHARED/PUBLICACOES_INTEGRATION_MATRIX.md)
