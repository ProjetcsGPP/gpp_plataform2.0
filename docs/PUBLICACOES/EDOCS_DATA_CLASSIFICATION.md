# Classificação dos dados da coleta E-Docs

**Versão:** `1.0-proposta`  
**Estado:** inventário preenchido; aprovação funcional e retenção pendentes  
**Escopo:** EDOC-01 a EDOC-05, seleção local, evidências e planilha mensal

Esta classificação atende documentalmente a `PRE-003`, mas não encerra o gate
enquanto o dono da informação não aprovar divulgação, finalidade e retenção.

## 1. Classes usadas

| Classe | Regra |
|---|---|
| Público candidato | Campo institucional agregado que pode compor publicação após aprovação e workflow editorial |
| Gerencial | Campo usado em preparação, conferência, proveniência ou operação autenticada |
| Restrito operacional | Identificador ou artefato técnico desnecessário ao público e limitado aos operadores autorizados |
| Segredo | Credencial ou prova de autenticação; nunca persiste em snapshot, planilha, log ou DTO |
| Quarentena de schema | Campo novo/desconhecido, proibido em publicação até classificação explícita |

“Público candidato” não significa dado já autorizado. A API e a planilha de
apoio não substituem a publicação aprovada e imutável.

## 2. Matriz campo a campo

| Campo/artefato | Origem | Classificação proposta | Finalidade permitida | Distribuição pública v1 | Retenção |
|---|---|---|---|---:|---|
| `COD_MUNIC` | IBGE/lista local | Público candidato | Identificar município e permitir junção por código oficial | Sim, após aprovação | Vinculada ao snapshot publicado |
| `nomePatriarca` | E-Docs | Público candidato | Identificar ente institucional | Sim, após aprovação | Vinculada ao snapshot publicado |
| `nomeOrganizacao` | E-Docs | Público candidato | Detalhar unidade institucional, se o DTO público exigir esse nível | Condicional | Vinculada ao snapshot publicado |
| `totalProcessos` | E-Docs | Público candidato | Indicador mensal agregado | Sim, após aprovação | Vinculada ao snapshot publicado |
| `totalDocumentos` | E-Docs | Público candidato | Indicador mensal agregado | Sim, após aprovação | Vinculada ao snapshot publicado |
| `totalPaginas` | E-Docs | Público candidato | Indicador mensal agregado | Sim, após aprovação | Vinculada ao snapshot publicado |
| `mes` e `ano` | Parâmetro | Público candidato | Competência dos indicadores | Sim | Vinculada ao snapshot publicado |
| `idPatriarca` | E-Docs | Restrito operacional | Consulta, merge, deduplicação e rastreabilidade | Não por padrão | Conforme evidência operacional |
| `idOrganizacao` | E-Docs | Restrito operacional | Merge, deduplicação e rastreabilidade | Não por padrão | Conforme evidência operacional |
| `sigla` | E-Docs/EDOC-05 | Gerencial | Conferência e seleção | Não na v1 | Conforme evidência operacional |
| `tipoAgente` | E-Docs/EDOC-05 | Gerencial | Validar natureza do agente; códigos `1`, `2`, `3`, `4`, `5`, `6` e `99` | Não | Conforme evidência operacional |
| `descricaoTipoAgente` | E-Docs/EDOC-05 | Gerencial | Conferência do enum `Cidadao`, `Papel`, `Grupo`, `Unidade`, `Organizacao`, `Sistema` ou `NaoIdentificado` | Não | Conforme evidência operacional |
| `nomeConfigurado` | Lista local | Gerencial | Comparar configuração com catálogo remoto | Não | Enquanto a configuração estiver vigente |
| `municipio_implantado_sem_uso_edocs` | Decisão manual do gestor | Gerencial | Identificar município implantado que não utiliza o E-Docs | Não por padrão | Enquanto o cadastro e sua auditoria forem necessários |
| `municipio_implantado` | Decisão manual do gestor | Gerencial | Registrar implantação confirmada | Não por padrão | Enquanto o cadastro e sua auditoria forem necessários |
| `municipio_em_implantacao` | Decisão manual do gestor | Gerencial | Registrar implantação em andamento | Não por padrão | Enquanto o cadastro e sua auditoria forem necessários |
| `municipio_manifestou_interesse` | Decisão manual do gestor | Gerencial | Registrar manifestação de interesse | Não por padrão | Enquanto o cadastro e sua auditoria forem necessários |
| `MunicipioEdocs.codigo_ibge` e `nome` | Cadastro manual/IBGE | Público gerencial | Identificar município independentemente de patriarca E-Docs | Sim, no mapa congelado | Enquanto houver publicação e auditoria associada |
| `VigenciaSituacaoMunicipioEdocs.situacao` | Decisão manual do gestor | Gerencial | Registrar interesse, implantação ou implantação sem uso por competência | Sim, após congelamento na publicação | Enquanto houver publicação e auditoria associada |
| `nomeEdocs` | Catálogo normalizado | Gerencial | Detectar mudança de nomenclatura | Não | Conforme evidência operacional |
| `ambiente` | Configuração | Restrito operacional | Proveniência e diagnóstico | Não | Conforme evidência operacional |
| `coletado_em_utc` | Coletor | Gerencial | Rastrear instante da coleta | Somente se o DTO de proveniência aprovar | Conforme evidência operacional |
| código do método e endpoint | Coletor | Restrito operacional | Auditoria técnica | Não | Conforme evidência operacional |
| JSONs brutos | E-Docs | Restrito operacional | Evidência, reconciliação e diagnóstico | Nunca diretamente | Prazo institucional pendente |
| planilha XLSX operacional | Backend GPP | Restrito operacional | Apoiar preparação e conferência manual | Nunca diretamente | Prazo institucional pendente |
| campos adicionais não classificados | E-Docs | Quarentena de schema | Preservar evidência para análise | Não | Com a evidência bruta, sem ingestão pública |
| `client_id` OAuth | Acesso Cidadão/OpenBao | Restrito operacional | Identificar cliente técnico | Não | Enquanto a integração estiver ativa |
| `client_secret`, token e AppRole `secret_id` | Acesso Cidadão/OpenBao | Segredo | Autenticação técnica | Nunca | Somente no secret store/memória, conforme política de credenciais |
| AppRole `role_id`, paths e configuração OpenBao | OpenBao | Restrito operacional | Resolver identidade e segredo | Não | Enquanto a integração estiver ativa |
| logs seguros de status/latência | Backend GPP | Restrito operacional | Operação, alerta e auditoria | Não | Prazo de logs pendente |

## 3. Dados pessoais e sensíveis

Nos schemas observados não existem CPF, nome de pessoa, endereço, contato,
conteúdo de documento, assunto de processo ou outra informação pessoal. Os
nomes são de entes e organizações.

Essa conclusão vale somente para os campos inventariados. Qualquer campo novo
fica em quarentena; texto livre, identificação de pessoa, conteúdo documental
ou metadado de documento/processo é proibido na distribuição até nova análise.

## 4. Finalidades aprováveis

### Público candidato

- apresentar indicadores mensais agregados por município;
- identificar competência e fonte institucional;
- permitir comparação histórica somente após definição do DTO público e da
  política de histórico.

### Gerencial e operacional

- selecionar patriarcas;
- conferir nomes e códigos;
- reproduzir consultas e investigar divergências;
- preparar publicação e registrar proveniência;
- auditar autenticação e falhas sem registrar segredo ou corpo remoto.

É proibido usar os artefatos para inferir produtividade individual, expor
conteúdo de documentos/processos ou publicar diretamente a planilha/JSON.

## 5. Retenção e descarte

A política institucional ainda não foi definida. Até sua aprovação:

- não haverá descarte automático;
- `var/edocs` continuará sendo armazenamento local de trabalho, não repositório
  institucional nem backup;
- JSON e XLSX não poderão ser publicados nem enviados para local não aprovado;
- a futura ingestão deverá preservar versões imutáveis e hashes;
- a retenção de publicação pública será decidida com `PUB-024`;
- a retenção de logs e evidências será decidida com `PUB-022`.

Essa regra provisória evita perda silenciosa, mas não encerra `PRE-003` nem
autoriza conservação indefinida em produção.

## 6. Allowlist inicial para o futuro DTO público

Somente estes campos podem avançar para discussão em `PUB-017`:

```text
COD_MUNIC
nomePatriarca
nomeOrganizacao (condicional)
totalProcessos
totalDocumentos
totalPaginas
mes
ano
```

IDs técnicos, ambiente, endpoints, instante interno da coleta, artefatos brutos
e qualquer campo adicional ficam fora da allowlist pública inicial.

## 7. Aprovação necessária

| Decisão | Responsável | Estado |
|---|---|---|
| Confirmar dono da informação | Gestão do processo atual | Pendente |
| Autorizar os campos públicos candidatos | Dono da informação e gestão de `PUBLICACOES` | Pendente |
| Aprovar ou excluir detalhamento por organização | Dono da informação | Pendente |
| Definir retenção de JSON, XLSX e logs | Gestão, infraestrutura e segurança/privacidade | Pendente |
| Confirmar ausência de restrição contratual da origem | Responsável E-Docs/PRODEST | Pendente |

Após essas decisões, a versão aprovada substituirá o sufixo `proposta` e
registrará nomes, data e evidência.
