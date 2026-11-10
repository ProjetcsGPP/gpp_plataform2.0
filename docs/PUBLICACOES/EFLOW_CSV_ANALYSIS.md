# Análise inicial do CSV de definições disponíveis do E-Flow

**Arquivo observado:** `E-Flow_Definições_de_Fluxo_disponíveis_(20261110_103545).csv`  
**Data indicada no nome:** 2026-11-10 10:35:45  
**Estado:** fonte, indicadores e importação administrativa implementados;
contrato de publicação ainda pendente  
**SHA-256:** `74a668fdc333ff7ceec3a1f1ecb3b5c42752e3b8eab6401e6a6ee1a4173ba809`

## 1. Origem e limite da evidência

O arquivo é exportado manualmente pelo site E-Flow Admin. Segundo o responsável
do projeto, essas informações não estão disponíveis pela API atualmente. O CSV
será a fonte da coleta E-Flow para os indicadores definidos na seção 4. Esta
decisão não autoriza publicação, não define agendamento e não comprova
estabilidade do schema ou dos identificadores.

O CSV não foi copiado para o repositório nem alterado.

## 2. Estrutura observada

| Propriedade | Valor observado |
|---|---:|
| Encoding | UTF-8 com BOM |
| Terminador de linha | CRLF |
| Delimitador | `;` |
| Registros de dados | 1.016 |
| Colunas por registro | 7 em todos os registros |
| Campos vazios | 0 |
| Linhas integralmente duplicadas | 0 |
| IDs distintos e UUID válidos | 1.016 |

As colunas são:

| Coluna | Cardinalidade observada | Interpretação inicial |
|---|---:|---|
| `ID` | 1.016 | Identificador candidato da definição; estabilidade pendente de confirmação |
| `Nome` | 1.012 | Nome exibido; não é chave, pois há nomes repetidos com IDs diferentes |
| `Versão` | 30 valores | Inteiro entre 1 e 62; sem semântica de versionamento confirmada |
| `Público-alvo` | 5 | Classificação observada da audiência |
| `Patriarca` | 12 | Texto com sigla e nome do patriarca |
| `Órgão` | 67 textos; 69 identidades compostas | Texto com sigla e nome; o arquivo não fornece ID do órgão |
| `Setor` | 176 textos; 182 identidades compostas | Texto com sigla e nome; o arquivo não fornece ID do setor |

Distribuição de `Público-alvo`:

| Valor | Registros |
|---|---:|
| Cidadão | 722 |
| Órgão | 183 |
| Patriarca | 108 |
| Setor | 2 |
| Lista de Permissão | 1 |

## 3. Distribuição por patriarca

| Patriarca | Definições |
|---|---:|
| GOVES | 923 |
| PMMARATA | 19 |
| PMSMJ | 17 |
| PMAV | 13 |
| PMVA | 13 |
| PMICNH | 11 |
| PMIUNA | 11 |
| PMAB | 3 |
| PMBJN | 2 |
| PMITAG | 2 |
| PMAL | 1 |
| PMPIUMA | 1 |

O arquivo contém o Estado e 11 municípios. As 12 siglas foram encontradas no
catálogo local `patriarca_edocs`; nenhuma ficou sem correspondência por sigla.
Essa comparação não autoriza vínculo definitivo apenas pelo texto: a importação
deverá registrar a forma original e tratar mudança ou ambiguidade como
divergência.

## 4. Indicadores confirmados

Os cálculos canônicos serão realizados pelo backend sobre um snapshot validado.
O frontend receberá valores e percentuais prontos, sem recalculá-los.

| Indicador | Regra inicial | Valor neste arquivo |
|---|---|---:|
| Total de Fluxos | quantidade de registros com `ID` válido e único | 1.016 |
| Órgãos Participantes | combinações distintas de `Patriarca` + `Órgão`, após remoção de espaços periféricos | 69 |
| Setores Ativos | combinações distintas de `Patriarca` + `Órgão` + `Setor`, após remoção de espaços periféricos | 182 |
| Órgãos com maior quantidade de Fluxos | cinco maiores contagens por identidade composta de órgão | tabela abaixo |
| Distribuição por público-alvo | contagem e percentual sobre o total de fluxos | tabela abaixo |

O nome “Setores Ativos” representa, neste contrato inicial, setores presentes
na exportação de definições disponíveis. O arquivo não possui um campo de
situação próprio; portanto, a origem ainda deve confirmar essa equivalência.

### 4.1 Cinco órgãos com mais fluxos

| Órgão | Fluxos | Percentual do total |
|---|---:|---:|
| SEGER — Secretaria de Estado de Gestão e Recursos Humanos | 112 | 11,02% |
| IDAF — Instituto de Defesa Agropecuária e Florestal do ES | 91 | 8,96% |
| SESA — Secretaria de Estado da Saúde | 72 | 7,09% |
| ESESP — Escola de Serviço Público do Espírito Santo | 64 | 6,30% |
| SEFAZ — Secretaria de Estado da Fazenda | 54 | 5,31% |
| Outros | 623 | 61,32% |

Os cinco maiores representam 393 fluxos e 38,68% do total. A fatia `Outros`
deve integrar o gráfico de pizza para que o círculo represente 100% dos fluxos.
O percentual de cada fatia é `quantidade / 1.016 × 100`, arredondado para duas
casas decimais apenas na apresentação.

### 4.2 Distribuição por público-alvo

| Público-alvo | Fluxos | Percentual do total |
|---|---:|---:|
| Cidadão | 722 | 71,06% |
| Órgão | 183 | 18,01% |
| Patriarca | 108 | 10,63% |
| Setor | 2 | 0,20% |
| Lista de Permissão | 1 | 0,10% |

### 4.3 Perfil consolidado para publicação

A evidência visual da publicação manual anterior confirmou uma segunda regra,
mantida separada do resultado técnico completo. Em
`CONSOLIDADO_PUBLICACAO`, órgãos e setores são distintos apenas pelo texto
normalizado, não por sua composição com patriarca; o gráfico usa os cinco
maiores sem `Outros` e recalcula o percentual sobre os cinco; a distribuição
exibe somente Cidadão, Órgão e Patriarca e recalcula o percentual sobre essas
categorias.

Aplicado ao arquivo atual, esse perfil produz 1.016 fluxos, 67 órgãos e 176
setores. Os cinco maiores somam 393 fluxos; as três categorias de público-alvo
exibidas somam 1.013. Os dados excluídos da apresentação permanecem preservados
no snapshot e no perfil `COMPLETO_TECNICO`.

Os dois resultados são sempre consultáveis. Uma preferência individual,
inicialmente `CONSOLIDADO_PUBLICACAO`, controla apenas qual perfil a tela exibe
primeiro. O usuário pode alterá-la sem justificativa; a mudança produz log e
auditoria, mas não altera o snapshot nem os resultados.

## 5. Qualidade e limitações

- há 63 nomes e 14 setores com espaço no final; a comparação pode usar valor
  normalizado, mas a evidência bruta deve ser preservada;
- quatro nomes aparecem mais de uma vez e pertencem a IDs distintos;
- `Nome`, `Órgão` e `Setor` não podem ser usados isoladamente como identidade;
- o arquivo não informa data de criação, alteração, ativação ou desativação;
- não há identificadores estruturados de órgão e setor;
- um único arquivo não permite concluir se `ID` permanece estável entre
  exportações nem como `Versão` evolui;
- presença no arquivo indica definição disponível no instante da exportação,
  mas não comprova uso efetivo, quantidade de instâncias ou implantação
  oficialmente concluída;
- ausência em exportação futura não deve provocar exclusão automática.

## 6. Contrato implementado para a coleta

A importação trata cada arquivo como snapshot manual versionado:

1. receber o CSV em quarentena e calcular hash antes do parsing;
2. preservar o artefato original e os metadados da importação;
3. validar encoding, delimitador, cabeçalho e quantidade de colunas;
4. usar `ID` como chave candidata da definição, mantendo o valor bruto;
5. normalizar espaços apenas na representação derivada;
6. relacionar o patriarca por regra aprovada, registrando divergências;
7. não apagar nem sobrescrever snapshots anteriores;
8. registrar início, conclusão ou falha em auditoria append-only;
9. manter os dados normalizados independentes da publicação;
10. devolver ao frontend o resultado e os indicadores canônicos da coleta.

Models, endpoints, permissões e detalhes operacionais estão descritos em
[`EFLOW_ADMIN_API.md`](./EFLOW_ADMIN_API.md). A associação de um snapshot a uma
publicação permanece deliberadamente fora deste recorte.

### 6.1 Primeira importação de conferência

Após a migração e o seed no banco configurado localmente, o arquivo analisado foi
importado pela mesma camada de serviço usada pela API:

- coleta: `b95d938f-2f5f-4835-a0ec-ae825d06e45a`;
- situação: `CONCLUIDA`;
- SHA-256: `74a668fdc333ff7ceec3a1f1ecb3b5c42752e3b8eab6401e6a6ee1a4173ba809`;
- definições normalizadas: 1.016;
- eventos de auditoria: início, cálculo dos perfis e conclusão;
- indicadores persistidos: 1.016 fluxos, 69 órgãos e 182 setores.

Essa evidência confirma a reprodução técnica do arquivo, mas a conferência com
a última publicação manual continua sendo a validação funcional seguinte.

Antes de usar a coleta para publicar conteúdo, ainda é necessário confirmar:

- estabilidade e significado de `ID` e `Versão`;
- se o arquivo contém somente definições vigentes;
- significado oficial de presença e ausência;
- possibilidade de exportar IDs de órgão e setor;
- responsável funcional, classificação, retenção e autorização de divulgação;
- se o indicador de implantação municipal pode ou não ser derivado deste CSV.
