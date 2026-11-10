# Contrato da fonte E-Docs — quantitativos mensais

**Código:** `EDOCS_QUANTITATIVOS_MENSAIS_V1`  
**Versão documental:** `1.0-proposta`  
**Estado:** preenchido tecnicamente; pendente de responsáveis e aprovação  
**Escopo:** EDOC-01 a EDOC-05 e normalização operacional existente  
**Não autoriza:** publicação pública ou agendamento periódico automático. A
ingestão administrativa versionada foi implementada, mas continua sem
autorizar divulgação.

Este documento especializa o
[`SOURCE_CONTRACT_TEMPLATE.md`](./SOURCE_CONTRACT_TEMPLATE.md). Fatos
observados na API e no coletor estão separados de decisões ainda pendentes.

## 1. Identificação

| Campo | Definição |
|---|---|
| Código da fonte | `EDOCS_QUANTITATIVOS_MENSAIS_V1` |
| Nome | Quantitativos mensais de processos, documentos e páginas do E-Docs |
| Aplicação proprietária | E-Docs; proprietário institucional e autoridade para aprovar o contrato ainda devem ser confirmados |
| Responsável funcional da informação | Pendente de nomeação |
| Responsável técnico da origem | Pendente de confirmação pela gestão do E-Docs/PRODEST |
| Responsável técnico da integração | Desenvolvedor responsável pelo backend GPP; nome não registrado neste documento |
| Contato de incidente | Canal Zimbra do projeto após teste operacional; contato da origem permanece pendente |
| Ambientes | API de treinamento (`HML`) e API de produção (`PRD`), selecionadas explicitamente |
| Finalidade | Apoiar a preparação mensal da publicação hoje executada manualmente e preservar evidências da consulta |
| Base de classificação | Dados institucionais agregados; não foram observados dados pessoais nos campos selecionados. A autorização para divulgação permanece pendente |

Os responsáveis pendentes impedem a aprovação de `PRE-002`. A concentração
temporária das funções técnicas em uma pessoa não transfere a ela a
propriedade funcional dos dados do E-Docs.

## 2. Regra de disponibilização

### 2.1 Confirmado

- a API V2 retorna quantitativos para o mês e ano informados;
- EDOC-01 e EDOC-03 retornam totais por patriarca;
- EDOC-02 e EDOC-04 retornam totais por organização de um patriarca;
- EDOC-05 retorna o catálogo de patriarcas habilitados;
- a origem calcula `totalProcessos`, `totalDocumentos` e `totalPaginas`;
  `PUBLICACOES` não reconstruirá esses totais;
- não há, nos métodos selecionados, versão da competência, instante de
  fechamento, indicador de correção ou evento de nova versão;
- uma nova consulta da mesma competência pode retornar valores diferentes sem
  que a API informe a causa ou uma revisão identificável.

### 2.2 Pendente de confirmação pela origem

- quando uma competência pode ser considerada fechada ou canônica;
- se e por quanto tempo valores históricos podem ser corrigidos;
- se a resposta vazia representa zero, ausência de adesão ou indisponibilidade;
- estabilidade dos identificadores e nomes institucionais;
- SLA, limite de requisições e prazo de disponibilidade;
- contato e procedimento institucional para divergências.

Não existem simulação, prévia, cancelamento ou revogação representados nesses
relatórios. A ausência desses estados na resposta não comprova que a origem
seja imutável.

## 3. Mecanismo

| Item | Definição atual |
|---|---|
| Tipo | Polling HTTPS da API V2 por solicitação administrativa assíncrona |
| Evento ou agenda | Solicitação manual pela API; agenda periódica não aprovada |
| Identificador de revisão | Competência + número sequencial de revisão; somente uma revisão pode estar ativa por competência |
| Agregado operacional | `ResultadoMensalPatriarcaEdocs` e `ResultadoMensalOrganizacaoEdocs` |
| Versão da origem | Não fornecida |
| Cursor de reconciliação | Não fornecido; reconciliação exige nova consulta integral |
| Frequência/volume observado | Mensal; com 25 patriarcas, 53 GETs: catálogo, dois relatórios gerais e dois relatórios por patriarca |
| Timeout | 10 segundos para conexão e 60 segundos para leitura, configuráveis |
| Retry | Até duas repetições de GET idempotente para conexão, leitura, `429`, `502`, `503` e `504`, com backoff inicial de 0,5 segundo; um novo token após `401` |
| SLA da origem | Pendente |

O token OAuth2 usa `client_credentials` e escopo
`api-sigades-consultar`. Credenciais e tokens não compõem o snapshot.

## 4. Schema observado e normalizado

A classificação normativa está em
[`EDOCS_DATA_CLASSIFICATION.md`](./EDOCS_DATA_CLASSIFICATION.md).

| Campo | Tipo | Obrigatório na representação | Significado | Origem/regra |
|---|---|---:|---|---|
| `COD_MUNIC` | inteiro de 7 dígitos ou nulo | sim | Código IBGE do município | Mapeamento local validado no IBGE; nulo para não município |
| `idPatriarca` | UUID | sim | Identificador do patriarca | E-Docs |
| `nomePatriarca` | texto | sim | Nome institucional do patriarca | E-Docs ou nome da seleção na visão por organização |
| `idOrganizacao` | UUID | somente organização | Identificador da organização | E-Docs |
| `nomeOrganizacao` | texto | somente organização | Nome institucional da organização | E-Docs |
| `totalProcessos` | inteiro não negativo ou nulo | sim | Processos da competência; nulo quando a origem omite a dimensão | E-Docs, EDOC-01/02 |
| `totalDocumentos` | inteiro não negativo ou nulo | sim | Documentos da competência; nulo quando a origem omite a dimensão | E-Docs, EDOC-03/04 |
| `totalPaginas` | inteiro não negativo ou nulo | sim | Páginas da competência; nulo quando a origem omite a dimensão | E-Docs, EDOC-03/04 |
| `mes` | inteiro de 1 a 12 | sim | Mês consultado | Parâmetro do coletor |
| `ano` | inteiro de 1 a 9999 | sim | Ano consultado | Parâmetro do coletor |
| `ambiente` | enum `HML`/`PRD` | evidência | Ambiente consultado | Configuração explícita |
| `coletado_em_utc` | data/hora ISO 8601 | evidência | Instante da geração da planilha | Coletor |

EDOC-05 também pode retornar `sigla`, `tipoAgente` e
`descricaoTipoAgente`. Esses campos integram o catálogo operacional restrito
de patriarcas, mas não a representação pública proposta.

O código e a descrição do tipo devem formar um dos pares definidos pelo
contrato da API:

| `tipoAgente` | `descricaoTipoAgente` |
|---:|---|
| `1` | `Cidadao` |
| `2` | `Papel` |
| `3` | `Grupo` |
| `4` | `Unidade` |
| `5` | `Organizacao` |
| `6` | `Sistema` |
| `99` | `NaoIdentificado` |

Código desconhecido, descrição desconhecida ou par incompatível interrompe a
coleta e gera resultado auditável; o backend não corrige nem infere o tipo.

Campos adicionais recebidos são preservados na evidência operacional. Eles
não entram em snapshot nem DTO público sem nova classificação e alteração
versionada deste contrato.

### 4.1 Catálogo controlado de patriarcas

Decisão funcional registrada em 06/11/2026:

- EDOC-05 será consultado integralmente e cada resposta será preservada como
  uma observação identificada por execução e hash;
- todos os patriarcas retornados serão comparados com o catálogo definitivo;
- um patriarca novo, alterado, reativado ou ausente produzirá divergência
  pendente e alerta ao frontend;
- a resposta remota nunca incluirá, alterará ou desativará automaticamente um
  registro definitivo;
- inclusão, atualização, desativação ou manutenção exigem decisão explícita,
  justificativa, usuário e instante da revisão;
- catálogo remoto vazio é falha para validação, e não ordem para desativação em
  massa;
- `coletar_detalhes` identifica, entre os patriarcas ativos guardados, quais
  alimentarão EDOC-01 a EDOC-04;
- alterar `coletar_detalhes` também exige ação explícita, justificativa e evento
  de auditoria;
- `municipio_implantado_sem_uso_edocs` é indicador gerencial manual, não vem
  do EDOC-05 e não pode ser alterado pela sincronização remota;
- `codigo_municipio`, `municipio_implantado`, `municipio_em_implantacao` e
  `municipio_manifestou_interesse` também são campos locais manuais;
- alterar código ou indicadores exige permissão técnica, justificativa,
  incremento de versão e evento de auditoria com valores anterior e atual;
- eventos WebSocket informam apenas o resumo da execução ou decisão; o banco de
  dados permanece a fonte canônica para o frontend.

As tabelas operacionais separam catálogo definitivo, execução, observação,
divergência e evento de auditoria. Assim, a evidência recebida não é confundida
com uma alteração já aprovada pelo gestor.

| Finalidade | Entidade Django | Tabela |
|---|---|---|
| Catálogo definitivo | `PatriarcaEdocs` | `publicacoes.patriarca_edocs` |
| Execução da consulta | `ColetaPatriarcasEdocs` | `publicacoes.coleta_patriarcas_edocs` |
| Resposta normalizada | `ObservacaoPatriarcaEdocs` | `publicacoes.observacao_patriarca_edocs` |
| Alteração pendente | `DivergenciaPatriarcaEdocs` | `publicacoes.divergencia_patriarca_edocs` |
| Trilha de auditoria | `EventoAuditoriaPatriarcaEdocs` | `publicacoes.evento_auditoria_patriarca_edocs` |

Entidades, campos, estados, decisões, permissões e eventos próprios deste
domínio usam nomenclatura em português. Permanecem com a grafia original
somente as chaves recebidas do contrato externo (`tipoAgente` e
`descricaoTipoAgente`) e interfaces técnicas obrigatórias dos frameworks.
As novas tabelas usam a base compartilhada `ModeloAuditavel`, com os campos
`criado_por_id`, `criado_por_nome`, `atualizado_por_id`,
`atualizado_por_nome`, `criado_em` e `atualizado_em`; a base anterior foi
preservada apenas para não alterar retroativamente as demais aplicações.

## 5. Cálculos e responsabilidades

| Cálculo/regra | Responsável | Implementação canônica | Evidência |
|---|---|---|---|
| Total mensal de processos | E-Docs | EDOC-01/02 | JSON bruto da consulta |
| Total mensal de documentos | E-Docs | EDOC-03/04 | JSON bruto da consulta |
| Total mensal de páginas | E-Docs | EDOC-03/04 | JSON bruto da consulta |
| Correspondência processo/documento por identificador | Backend GPP | Merge por IDs estáveis retornados pela origem | Testes sintéticos do coletor |
| Competência | Backend GPP | Parâmetros `mes` e `ano` da consulta | Aba `Parâmetros` e paths consultados |
| Código municipal | Backend GPP | Lista versionada, validada contra o IBGE | `config/edocs/patriarcas_disponiveis.json` |

- [x] O backend não reconstrói totais exclusivos do domínio E-Docs.
- [x] O frontend não calculará valores canônicos.
- [ ] A origem confirmou formalmente a semântica e o fechamento da competência.
- [ ] Snapshots cruzados registrarão versões de todas as fontes utilizadas.

Não se deve somar organizações para substituir o total do patriarca sem
contrato explícito da origem.

## 6. Segurança e classificação

- [x] Campos conhecidos foram inventariados e receberam classificação
  proposta.
- [x] OAuth2, escopo e armazenamento externo de segredos estão definidos.
- [x] Erros do cliente não incluem credenciais nem corpo remoto.
- [x] HML e PRD possuem configurações e identidades OpenBao independentes.
- [ ] Egress foi aprovado no nível de rede.
- [ ] Retenção e descarte institucional foram aprovados.
- [ ] O proprietário autorizou a publicação dos campos candidatos a públicos.
- [ ] Testes contratuais com a origem foram acordados.

Os JSONs brutos e a planilha são artefatos operacionais restritos, mesmo
quando contêm somente campos candidatos a públicos. Divulgação ocorrerá apenas
por publicação aprovada e imutável.

## 7. Falhas, correções e recuperação

| Situação | Tratamento atual ou obrigatório |
|---|---|
| Origem indisponível | A execução falha sem gerar uma planilha parcial nova; não há fallback automático |
| Uso da última competência disponível | Somente após regra editorial aprovada, com competência, idade, fonte afetada e justificativa visíveis |
| Resposta vazia | Não inferir zero; interromper ou colocar em revisão até a origem confirmar a semântica |
| Retry esgotado | Falha segura; não existe dead-letter porque a execução ainda é manual |
| Reconciliação | Reexecutar integralmente a competência e comparar com a evidência anterior |
| Correção da origem | Produzir nova versão; nunca alterar uma publicação vigente |
| Divergência | Preservar as duas evidências e registrar decisão do gestor |
| Reprocessamento | Responsável técnico executa; aprovação funcional permanece pendente |

### Versionamento implementado

Cada solicitação persistida recebe UUID, competência, revisão sequencial,
ambiente, seleção congelada, instantes, situação, contagens e hash do resultado.
Uma reexecução cria nova revisão e preserva as respostas brutas anteriores. O
coletor de planilha continua sendo uma saída operacional independente e pode
substituir arquivos do mesmo diretório; ele não é o repositório canônico.

## 8. Critérios de aceite

- [ ] Responsáveis funcional e técnico da origem nomeados.
- [ ] Semântica, fechamento e correção da competência confirmados.
- [x] Snapshot reproduzível e imutável por revisão administrativa.
- [x] Reexecução cria nova revisão e não sobrescreve evidência anterior.
- [ ] Indisponibilidade não produz publicação incompleta.
- [x] Campos desconhecidos não são autorizados automaticamente para o DTO.
- [x] Existem testes sintéticos para autenticação, merge e exportação.
- [ ] Retenção, observabilidade e alertas aprovados.
- [ ] Classificação campo a campo aprovada.
- [ ] Contrato aprovado pelos papéis abaixo.

## 9. Aprovações pendentes

| Papel | Nome | Decisão | Data | Evidência |
|---|---|---|---|---|
| Responsável funcional da informação | Pendente | Pendente | — | — |
| Responsável técnico do E-Docs/PRODEST | Pendente | Pendente | — | — |
| Gestão de `PUBLICACOES` | Pendente | Pendente | — | — |
| Segurança/privacidade | Pendente, se exigido | Pendente | — | — |

Enquanto esta seção não for aprovada, o coletor permanece ferramenta de apoio
e não fonte oficial de publicação.
