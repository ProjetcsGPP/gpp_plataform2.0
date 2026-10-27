# ADR-0004 — Renderização híbrida do Portal

**Status:** aceito  
**Data:** 2026-10-26  
**Matriz:** `PUB-013`

## Contexto

O frontend atual usa CSR, Axios relativo a `/api`, Zustand e SWR global. Esse
conjunto continuará adequado para áreas autenticadas, mas o Axios singleton é
acoplado ao estado do browser e não pode ser reutilizado por múltiplas
requisições no servidor. O dashboard público precisa de entrega inicial
estável, metadados e possibilidade de indexação.

## Decisão

Adotar estratégia híbrida:

- `/portal` renderiza no servidor o conteúdo público inicial e hidrata somente
  os componentes interativos necessários;
- `/portal/dashboard` e demais áreas internas permanecem CSR;
- SSR usa adaptador server-only e origem interna configurada por variável não
  pública;
- SSR não importa o Axios singleton, Zustand, stores ou interceptors do browser;
- cookies, sessão e `Authorization` do visitante não são encaminhados à API
  pública;
- componentes client-side públicos usam o Axios compartilhado com
  `gppAuthMode: "public"` e credenciais desabilitadas para essa requisição;
- falhas da API pública geram estado público controlado e nunca redirecionamento
  para login.

## Isolamento por requisição

Dados SSR vivem apenas no escopo da requisição ou em cache público cuja chave
inclui endpoint, versão de schema e representação. Nenhum objeto mutável de
usuário, sessão ou aplicação será singleton no servidor.

## Critérios de aceite

- duas renderizações concorrentes com cookies diferentes produzem a mesma
  representação pública;
- nenhum cookie ou header de autorização chega ao endpoint público pelo SSR;
- build impede importação do cliente browser-only no grafo server-only;
- erro público não limpa store autenticada nem abre login;
- hidratação não mistura fallback SSR e dados administrativos;
- metadados e conteúdo textual essencial existem sem JavaScript.
