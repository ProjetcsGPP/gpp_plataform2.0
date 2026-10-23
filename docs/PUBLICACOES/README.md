# Gestão e Distribuição de Informações Públicas

**Status:** proposta arquitetural para validação  
**Branch inicial:** `feat/publicacoes-informacoes`  
**Última revisão:** 2026-10-23

Este diretório reúne a documentação de planejamento da futura aplicação
`PUBLICACOES`. A documentação precede a implementação: itens descritos como
pendentes ou exemplos não autorizam alteração de regra de negócio em aplicações
de origem.

Antes de iniciar ou atualizar qualquer trabalho deste escopo, é obrigatória a
leitura da
[matriz integrada compartilhada](../SHARED/PUBLICACOES_INTEGRATION_MATRIX.md).
Decisões transversais devem ser atualizadas nela conforme o
[protocolo comum](../SHARED/README.md).

## Objetivo

Criar uma aplicação capaz de:

- receber ou coletar informações de fontes internas e externas;
- preservar origem, versão, evidências e histórico;
- validar, transformar, agregar e calcular informações;
- formar publicações imutáveis, revisáveis e rastreáveis;
- distribuir conteúdo público por API;
- alimentar o dashboard público do Portal;
- administrar aplicações consumidoras e suas credenciais;
- manter autenticação de pessoas separada da autenticação de sistemas.

## Documentos

| Documento | Finalidade |
|---|---|
| [Matriz integrada compartilhada](../SHARED/PUBLICACOES_INTEGRATION_MATRIX.md) | Fonte de coordenação transversal entre backend, frontend, Portal, IAM, infraestrutura e aplicações de origem |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Escopo, limites, fluxo de dados, integração e decisões arquiteturais |
| [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) | Fases, entregáveis, dependências, critérios de saída e validações |
| [SECURITY_PLAN.md](./SECURITY_PLAN.md) | Threat model, controles obrigatórios e gates de segurança |
| [OPERATIONS_GUIDE.md](./OPERATIONS_GUIDE.md) | Como gestores, administradores e consumidores operarão a solução |
| [SOURCE_CONTRACT_TEMPLATE.md](./SOURCE_CONTRACT_TEMPLATE.md) | Formulário obrigatório para integrar uma fonte sem presumir suas regras |
| [CONSUMER_REGISTRATION_TEMPLATE.md](./CONSUMER_REGISTRATION_TEMPLATE.md) | Formulário para cadastrar aplicação consumidora e autorizar escopos |

## Vocabulário normativo

- **Decisão:** orientação aceita para a implementação inicial.
- **Proposta:** orientação que ainda requer confirmação antes de ser implementada.
- **Pendente:** assunto sem decisão suficiente.
- **Exemplo não normativo:** ilustração que não define comportamento de uma
  aplicação de origem.
- **Gate:** condição obrigatória para encerrar uma fase.

## Decisões aceitas até aqui

1. A aplicação será um bounded context próprio, inicialmente dentro do monólito
   Django, com o código interno `PUBLICACOES`.
2. O conteúdo público será servido a partir de publicações aprovadas e
   imutáveis, nunca diretamente de tabelas operacionais.
3. Aplicações de origem continuarão responsáveis por suas regras canônicas.
4. Integrações internas usarão notificação transacional seguida da obtenção de
   snapshot versionado, com reconciliação periódica.
5. Enquanto as aplicações estiverem no mesmo backend, a integração não usará
   HTTP interno desnecessário.
6. Gatilhos e conteúdos fornecidos por cada aplicação serão definidos com seus
   responsáveis; os exemplos deste planejamento não constituem essa definição.
7. A primeira versão terá um único perfil funcional de negócio,
   `GESTOR_PUBLICACOES`, sustentado por permissões técnicas granulares.
8. Consumidores de API são identidades de máquina e não perfis de usuário.

## Decisões ainda necessárias

- Nome funcional final apresentado aos usuários.
- Política de aprovação por uma ou duas pessoas.
- Quais conjuntos de dados serão usados no primeiro piloto.
- Classificação pública, gerencial ou restrita de cada campo.
- Infraestrutura de object storage, antivírus, gateway e secrets manager.
- Provedor institucional para autenticação máquina-a-máquina.
- Retenção de artefatos, eventos, logs e publicações revogadas.
- SLA, RPO, RTO e responsáveis por incidentes.

## Regra para exemplos de integração

Qualquer referência a eventos como “ativação”, “homologação” ou “conclusão” é
somente um exemplo técnico. Um evento só se torna contrato depois de:

1. validação pelo responsável da aplicação de origem;
2. definição do significado e momento exatos;
3. classificação dos dados fornecidos;
4. definição de versão e compatibilidade do schema;
5. testes de contrato;
6. registro no catálogo de fontes da aplicação `PUBLICACOES`.
