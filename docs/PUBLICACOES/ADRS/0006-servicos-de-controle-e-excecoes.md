# ADR-0006 — Serviços de controle e exceções governadas

**Status:** aceito  
**Data:** 2026-10-26

## Contexto

Storage, scanner, secrets manager, gateway e demais ferramentas poderão mudar
entre ambientes. Chamadas diretas a produtos concretos espalhariam regras de
segurança e criariam bypasses difíceis de auditar.

Também existem situações operacionais isoladas em que um resultado
inconclusivo ou uma restrição não crítica pode exigir tratamento excepcional.
Uma flag genérica de bypass transformaria esse tratamento em vulnerabilidade.

## Decisão

Cada camada de segurança terá serviço lógico, contrato versionado, veredicto,
política e evidência. Implementações concretas ficarão atrás de adapters e
deverão passar pela suíte comum de contrato.

Ordens excepcionais serão processadas pelo `SecurityOrderService`. O gestor é
a autoridade: seleciona controle, operação e recurso/hash, registra a
justificativa e aprova ou rejeita. Uma aprovação válida deve ser executada e o
resultado registrado. O veredicto original será preservado.

Não haverá parâmetro funcional oculto para ignorar segurança. A ordem será uma
entidade explícita. Somente autenticação da autoridade, justificativa,
identificação do alvo e gravação da ordem/resultado são requisitos para que a
aplicação reconheça a decisão.

Um alerta continuará registrado. Se o gestor justificar e ordenar prosseguir,
a aplicação não declara tecnicamente “falso positivo”: registra a declaração e
a ordem do gestor e executa para o mesmo hash.

## Consequências

- ferramentas podem mudar sem alterar a regra de negócio;
- DEV, HML e PRD executam a mesma suíte de contrato;
- falhas e exceções ficam rastreáveis;
- existe custo adicional de adapters, estados e testes;
- alguns controles podem ser serviços Python no início, sem exigir um
  microserviço de rede para cada contrato;
- novas categorias de controle reutilizam o mesmo contrato de ordem justificada.

## Referência normativa

O catálogo, DTOs, workflows e regras de exceção estão em
[`SECURITY_CONTROL_CONTRACTS.md`](../SECURITY_CONTROL_CONTRACTS.md).
