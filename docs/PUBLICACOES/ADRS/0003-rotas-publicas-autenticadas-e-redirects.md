# ADR-0003 — Rotas públicas, autenticadas e redirects

**Status:** aceito  
**Data:** 2026-10-26  
**Matriz:** `PUB-012`

## Contexto

Hoje `/` encaminha para `/portal/login` e o proxy protege todo prefixo
`/portal`, exceto login e manutenção. O novo Portal precisa apresentar conteúdo
público antes da autenticação e preservar links existentes sem abrir caminho
para redirect externo ou liberação acidental das rotas administrativas.

## Decisão

| Rota | Acesso | Comportamento |
|---|---|---|
| `/` | Público | Redirect permanente/controlado para `/portal`. |
| `/portal` | Público | Dashboard público canônico; pode abrir o login modal. |
| `/portal?login=1` | Público | Dashboard com solicitação explícita de abertura do modal. |
| `/portal/login` | Público | Compatibilidade; redireciona para `/portal?login=1`. |
| `/portal/dashboard` | Autenticado | Dashboard interno e aplicações disponíveis. |
| `/portal/aplicacoes` | Autenticado | Área interna conforme permissões. |
| `/portal/usuarios` | Autenticado | Área administrativa conforme permissões. |

O layout de `/portal` será neutro. Route groups ou estrutura equivalente
separarão os layouts público e autenticado sem mudar as URLs.

O proxy reconhecerá `/portal` como público apenas por igualdade exata. Não será
usado `startsWith("/portal")` para liberar o prefixo inteiro.

## Redirect pós-login

O destino será aceito somente quando:

- for caminho relativo iniciado por uma única `/`;
- pertencer a uma allowlist central de rotas autenticadas do Portal;
- não for rota de login, logout, manutenção ou acesso negado;
- não contiver origem, esquema, `//`, barra inversa, caractere de controle ou
  codificação ambígua de separadores;
- continuar válido após normalização e decodificação.

O fallback é `/portal/dashboard`. A mesma função será usada pelo login modal,
pela rota compatível e pelo tratamento de sessão expirada.

## Consequências e testes

- sessão existente não muda a representação da API pública;
- visitante pode consultar `/portal` sem cookie;
- acesso direto à área autenticada sem sessão encaminha ao contexto de login;
- sessão inválida é confirmada pelo backend, não apenas pela presença do cookie;
- testes cobrem URLs externas, scheme-relative, backslash, encoded slash,
  destinos fora da aplicação e loops para login;
- favoritos antigos de `/portal/login` continuam funcionais.
