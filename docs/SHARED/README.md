# Documentos compartilhados entre aplicações

**Escopo:** decisões e contratos que afetam mais de uma aplicação ou
repositório  
**Autoridade:** coordenação transversal; não substitui ADR, OpenAPI, contrato
de fonte ou documentação operacional detalhada  
**Última revisão:** 2026-10-23

Esta pasta é a referência comum mantida no repositório backend. Chats e equipes
que trabalhem em qualquer aplicação afetada devem consultar estes documentos
antes de propor ou implementar mudanças e atualizá-los quando uma decisão,
contrato, fase, bloqueio ou critério de aceite transversal mudar.

## Documentos disponíveis

| Documento | Escopo |
|---|---|
| [PUBLICACOES_INTEGRATION_MATRIX.md](./PUBLICACOES_INTEGRATION_MATRIX.md) | Matriz consolidada de decisões, responsáveis, contratos, fases, segurança e aceite de `PUBLICACOES`, Portal e integrações |

## Protocolo obrigatório para chats e equipes

1. No início de trabalho relacionado ao escopo, ler este índice, a matriz
   compartilhada e os documentos locais da aplicação envolvida.
2. Citar o ID estável da matriz em planos, ADRs, contratos, issues e PRs que
   tratem de uma linha existente.
3. Não converter exemplo, hipótese ou conversa em decisão. Registrar como
   `INSUMO`, `PROPOSTA` ou `PENDENTE` até a validação do responsável indicado.
4. Quando houver uma decisão aprovada, atualizar na mesma entrega:
   a linha da matriz, o contrato ou ADR especializado afetado e o histórico de
   alterações da matriz.
5. Não alterar unilateralmente uma decisão cujo responsável pertença a outra
   área. Registrar o novo insumo e solicitar a validação indicada.
6. Se documentos divergirem, interromper a implementação do ponto conflitante,
   registrar o conflito na matriz e resolvê-lo com os responsáveis. A matriz
   determina o estado de coordenação; o contrato especializado aprovado
   determina os detalhes executáveis.
7. Nunca registrar segredos, tokens, credenciais ou dados pessoais nestes
   documentos.

Uma leitura sem mudança material não exige edição. Atualizações devem preservar
o histórico: decisões substituídas não são apagadas e devem apontar para a linha
ou documento sucessor.

