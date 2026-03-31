# Integração Next.js com o backend GPP

## Resumo

O frontend Next.js deve consumir o backend por sessão, sem JWT e sem armazenar token em localStorage.
O browser recebe o cookie `gpp_session` e o envia automaticamente em requisições com `credentials: 'include'`.

## Variáveis de ambiente

Use uma variável pública para a URL base do backend.

```env
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

## Regras obrigatórias no fetch

Sempre use:

```ts
credentials: 'include'
```

Isso é necessário para enviar o cookie de sessão do Django em chamadas de login, logout, `me`, switch de aplicação e APIs protegidas.

## Fluxo de autenticação

### Login

1. Buscar aplicações públicas do backend.
2. O usuário escolhe a aplicação e informa credenciais.
3. Fazer `POST /api/accounts/login/` com `username`, `password` e `app_context`.
4. Se o backend aceitar, o cookie `gpp_session` será salvo pelo browser.

### Depois do login

- Chamar `GET /api/accounts/me/` para obter usuário, perfil, roles e apps acessíveis.
- Redirecionar conforme o `app_context` atual.
- Recarregar navegação e permissões com base no contexto atual.

### Troca de aplicação

Se o usuário tiver acesso a mais de uma app:

1. Entrar primeiro no Portal ou diretamente na app desejada.
2. Listar as apps permitidas pelo endpoint autenticado.
3. Ao clicar em outra app, chamar `POST /api/accounts/switch-app/` com o novo `app_context`.
4. Recarregar o estado da sessão e da interface.

## O que o frontend não deve fazer

- Não ler `gpp_session` via JavaScript.
- Não salvar credenciais ou sessão em localStorage.
- Não assumir que o cookie é `sessionid`.
- Não tratar acesso ao Portal como equivalente a acesso às outras apps.

## Casos suportados

| Cenário | Resultado esperado |
|---|---|
| Login direto em uma app com role | Sessão criada e contexto definido |
| Login no Portal por PORTAL_ADMIN | Sessão criada com contexto Portal |
| Entrar no Portal e mudar para outra app | Switch de contexto sem trocar o cookie |
| Entrar direto numa app específica | Sessão já nasce no contexto correto |
| Fazer logout | Sessão revogada e cookie removido |

## Casos não suportados

| Cenário | Resultado |
|---|---|
| Tentar login no Portal sem ser admin | Rejeitado pelo backend |
| Tentar trocar para app sem role | Rejeitado pelo backend |
| Fazer request protegida sem credentials | Cookie não é enviado |
| Tentar usar JWT | Não existe suporte |

## Estrutura sugerida no Next.js

- `lib/api.ts`: wrapper de fetch com `credentials: 'include'`.
- `lib/auth.ts`: funções de login, logout, `me`, `switchApp`.
- `app/login/page.tsx`: formulário de login.
- `app/(protected)/layout.tsx`: proteção por sessão no server side.
- `components/app-switcher.tsx`: seletor de aplicação para Portal Admin.

## Exemplo de wrapper

```ts
const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL!

export async function apiFetch(path: string, init: RequestInit = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
  })

  return res
}
```

## Exemplo de login

```ts
await apiFetch('/api/accounts/login/', {
  method: 'POST',
  body: JSON.stringify({
    username,
    password,
    app_context,
  }),
})
```

## Exemplo de troca de app

```ts
await apiFetch('/api/accounts/switch-app/', {
  method: 'POST',
  body: JSON.stringify({
    app_context: 'ACOES_PNGI',
  }),
})
```

## Observação importante

O cookie continua sendo o mesmo durante o switch de contexto.
O que muda é o contexto interno da sessão e, por consequência, as permissões carregadas pelo backend.
