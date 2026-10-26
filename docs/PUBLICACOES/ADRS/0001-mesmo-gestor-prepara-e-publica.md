# ADR-0001 — Mesmo gestor prepara e publica

**Status:** aceito  
**Data:** 2026-10-23  
**Matriz:** `PUB-009`

## Contexto

A operação inicial não dispõe de pessoas distintas para separar preparação e
publicação. A primeira versão já prevê um único perfil funcional,
`GESTOR_PUBLICACOES`, apoiado por permissões técnicas granulares.

## Decisão

O mesmo usuário poderá preparar e publicar uma versão, desde que esteja
autorizado para cada ação. Não será implementada uma regra que exija atores
distintos na primeira versão.

## Consequências e controles

- preparação e publicação continuam sendo transições distintas;
- o histórico registra ator, instante, estado anterior, estado posterior e
  justificativa de cada transição;
- permissões, validação, concorrência e imutabilidade permanecem obrigatórias;
- publicação, substituição e revogação terão testes positivos e negativos;
- uma futura segregação de funções exigirá nova decisão e migração compatível.

## Critério de aceite

Um gestor autorizado consegue preparar e publicar a mesma versão; um usuário
sem a permissão necessária é rejeitado; o histórico permite reconstruir as duas
ações mesmo quando realizadas pela mesma pessoa.
