# ADR-0005 — Fronteiras de cache público e autenticado

**Status:** aceito  
**Data:** 2026-10-26  
**Matriz:** `PUB-014`

## Contexto

O frontend possui cache SWR global e o backend possui Memcached, mas não há
contrato de cache HTTP para conteúdo público. O Axios envia credenciais por
padrão. Sem fronteiras explícitas, sessão, preview ou rascunho podem contaminar
uma representação pública, e uma revogação pode continuar aparecendo como
vigente.

## Decisão HTTP

| Representação | Política mínima |
|---|---|
| Ponteiro/dashboard vigente | `public, max-age=0, s-maxage=30, must-revalidate` |
| Sem publicação vigente | Revalidação obrigatória; cache compartilhado máximo de 15 segundos |
| Publicação imutável ainda pública | TTL longo permitido, com `ETag` e `Last-Modified` |
| Preview, rascunho e administração | `private, no-store` |
| Erro autenticado ou com detalhe interno | `private, no-store` |

O dashboard vigente terá `ETag` derivado de `publication_id`, versão do schema
e hash da representação; `Last-Modified` refletirá a publicação vigente. Uma
requisição condicional válida retornará `304` sem corpo.

A resposta pública:

- não varia por cookie, sessão ou autorização;
- não envia `Set-Cookie` por efeito da consulta;
- não inclui `Vary: Cookie` ou `Vary: Authorization`;
- não recebe headers de autenticação do SSR;
- possui limite de tamanho e paginação quando aplicável.

Publicação, substituição e revogação disparam invalidação do ponteiro vigente
após o commit. Falha de purge é observável e repetível; o TTL compartilhado
curto limita a janela residual.

`stale-if-error` é proibido no ponteiro vigente. Pode ser habilitado apenas em
representação imutável cuja classificação e política de histórico confirmem que
ela continua pública durante a falha. Revogação remove essa autorização e exige
purge.

## Decisão SWR e Next.js

- área pública e área autenticada usam providers SWR diferentes;
- chaves públicas começam por `publicacoes:public:v1`;
- chaves administrativas começam por `publicacoes:admin:v1`;
- preview usa provider efêmero e não persiste dados;
- login/logout não convertem cache público em cache autenticado;
- revalidação do ponteiro ocorre por `ETag` e por evento de publicação;
- fallback SSR contém somente o DTO público permitido;
- o cache do Next.js segue a mesma chave/versionamento e nunca inclui cookies.

## Critérios de aceite

- respostas públicas são idênticas com e sem cookies arbitrários;
- `If-None-Match` e `If-Modified-Since` produzem `304` corretamente;
- rascunho, preview e resposta autenticada nunca aparecem no cache público;
- publicação nova troca o ponteiro; revogação o remove;
- simulação de falha de purge converge dentro do TTL contratado;
- `stale-if-error` é rejeitado no ponteiro vigente e testado, quando habilitado,
  somente para recurso imutável ainda público;
- troca de sessão não reaproveita provider ou chave administrativa anterior.
