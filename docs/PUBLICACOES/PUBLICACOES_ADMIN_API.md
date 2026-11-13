# API administrativa de Publicações Institucionais

**Base:** `/api/pub-institucional/`  
**Autenticação:** sessão da aplicação `PUB_INSTITUCIONAL`  
**Início da série histórica:** janeiro de 2024

## 1. Separação entre coleta e publicação

Coletas E-Docs e E-Flow são snapshots independentes e imutáveis. O indicador
`coletar_detalhes` controla apenas futuras chamadas detalhadas ao E-Docs. Cada
publicação escolhe suas visões, congela a lista de patriarcas, referencia as
coletas usadas e persiste o resultado calculado. Não existe flag `publicada`
na coleta porque um snapshot pode atender várias publicações e visões.

## 2. Recursos

| Método | Rota | Permissão | Finalidade |
|---|---|---|---|
| `GET/POST/PATCH` | `visoes-publicacao/` | `view_*` / `configurar_visao_publicacao` | Consulta e mantém filtros editoriais |
| `GET/POST` | `publicacoes/` | `view_publicacao` / `add_publicacao` | Lista ou cria rascunho |
| `GET` | `publicacoes/{uuid}/` | `view_publicacao` | Consulta versão e competência |
| `POST` | `publicacoes/{uuid}/secoes/` | `change_publicacao` | Associa visão e snapshot a um rascunho |
| `POST` | `publicacoes/{uuid}/recalcular/` | `calcular_publicacao` | Filtra, calcula e valida todas as seções |
| `POST` | `publicacoes/{uuid}/reabrir/` | `change_publicacao` | Retorna candidato validado ao rascunho |
| `POST` | `publicacoes/{uuid}/remover-secao/` | `change_publicacao` | Remove seção de um rascunho |
| `GET` | `publicacoes/{uuid}/previa/` | `visualizar_previa_publicacao` | Retorna o conteúdo exato com `private, no-store` |
| `POST` | `publicacoes/{uuid}/publicar/` | `publicar_publicacao` | Congela e publica com justificativa |
| `POST` | `publicacoes/{uuid}/substituir/` | `substituir_publicacao` | Abre uma nova versão em rascunho |
| `POST` | `publicacoes/{uuid}/revogar/` | `revogar_publicacao` | Revoga a vigente com justificativa |
| `GET` | `historico-publicacoes/` | `view_historicopublicacao` | Consulta auditoria append-only |

Listagem aceita `ano_referencia`, `mes_referencia`, `situacao`, `search` e
`ordering`. Toda representação de publicação devolve:

```json
{
  "ano_referencia": 2024,
  "mes_referencia": 1,
  "competencia": "2024-01",
  "versao": 1,
  "situacao": "RASCUNHO"
}
```

## 3. Visões iniciais

O seed cria:

- `MUNICIPIOS_EDOCS`: patriarcas ativos com código IBGE;
- `GERAL_EFLOW`: todas as definições do snapshot vigente;
- `MUNICIPIOS_EFLOW`: definições dos patriarcas com código IBGE.

O escopo personalizado congela os IDs selecionados. No E-Flow, o filtro é
aplicado às linhas normalizadas antes do cálculo de totais, Top 5 e
percentuais. No E-Docs, a visão somente pode usar patriarcas presentes na
revisão bem-sucedida selecionada.

## 4. Escolha temporal das fontes

- E-Docs: revisão bem-sucedida de maior número da própria competência;
- E-Flow: snapshot concluído com maior competência inicial de vigência que não
  seja posterior à publicação;
- primeiro snapshot E-Flow: base retroativa vigente desde `01/2024`;
- snapshot novo: atende a competência informada e as seguintes até que outro
  snapshot passe a vigorar.

## 5. Workflow e concorrência

```text
RASCUNHO -> EM_VALIDACAO -> AGUARDANDO_PUBLICACAO -> PUBLICADA
PUBLICADA -> SUBSTITUIDA | REVOGADA
```

O cálculo congela configuração, patriarcas, perfil, resultado e hash de cada
seção. Publicar exige justificativa e `versao_registro`; valor desatualizado
retorna conflito. Uma versão publicada não aceita recálculo. A substituição
cria novo rascunho na mesma série e somente marca a anterior como substituída
quando a nova versão é efetivamente publicada.

## 6. Mapa municipal congelado no resultado E-Docs

Uma seção E-Docs municipal calculada contém `resultado.mapas` com o mapa
`IMPLANTACAO_EDOCS` na competência da publicação. A regra `V2` possui cinco
categorias:

- `IMPLANTADO_COM_USO_EDOCS`: a primeira atividade positiva observada na API
  oficial ocorreu até a competência; essa evidência prevalece;
- `IMPLANTADO_SEM_USO_EDOCS`: não há atividade observada até a competência e
  a situação manual já estava vigente;
- `EM_IMPLANTACAO`: processo de implantação informado pelo gestor estava
  vigente na competência;
- `MANIFESTOU_INTERESSE`: manifestação de interesse informada pelo gestor
  estava vigente na competência;
- `SEM_DADOS`: nenhuma das evidências anteriores está disponível.

O município é cadastrado separadamente do patriarca e não recebe ID externo
fictício. Código IBGE e nome são obrigatórios. As situações manuais possuem
vigência mensal e auditoria; quando existir uso observado pela API oficial,
essa evidência prevalece e atualiza automaticamente o cadastro municipal, sem
decisão adicional do usuário. O resultado congela código IBGE, nome, categoria,
legenda, cores, texto alternativo e proveniência. Municípios ausentes do
cadastro também são incluídos no DTO, a partir do catálogo do IBGE, com a
categoria `SEM_DADOS`. Assim, o frontend recebe todos os municípios de uma só
vez e usa o GeoJSON apenas para associar a geometria pelo `codigo_ibge`.

Esse mapa faz parte do snapshot administrativo imutável. A API pública projeta
uma allowlist desse conteúdo em `conteudo.mapas`, conforme o contrato versionado
de `PUB-017` descrito em `PUBLIC_DISTRIBUTION_CONTRACT.md`. A apresentação em
slides e os demais componentes visuais permanecem sob responsabilidade do
frontend e não alteram o snapshot canônico.

## 7. Séries históricas congeladas

Cada seção calculada contém `resultado.series_historicas`. O contrato é neutro
quanto ao componente visual: informa código, título, periodicidade, natureza,
unidade, precisão, completude e pontos mensais. Cabe ao frontend escolher
gráfico, cartão, tabela, slide e composição sem recalcular os valores.

Cada ponto anterior à competência da publicação usa, nesta ordem, o resultado
congelado de uma publicação válida da mesma visão ou a última coleta
bem-sucedida. A competência da própria publicação usa a seção que está sendo
calculada. Ausência de fonte gera valor nulo e origem `SEM_DADOS`, nunca zero
inferido.

No E-Docs, `valor_acumulado` é calculado pelo backend. No E-Flow, os valores
representam o estoque do snapshot vigente e não são acumulados entre meses. A
primeira base E-Flow continua retroativa a janeiro de 2024 e cada nova leitura
vale de sua competência inicial em diante.

Seções E-Docs também contêm
`resultado.consolidados_historicos_patriarcas`, com todos os patriarcas da visão
ordenados pela economia total acumulada. Cada item informa posição, município,
`codigo_municipio`, `nome_municipio`, quantidade de competências e os mesmos
indicadores canônicos acumulados. O nome é obtido do catálogo oficial do IBGE
congelado durante o recálculo, e não do nome organizacional do patriarca. Esse
resultado permite ao frontend escolher quantos municípios exibir no ranking
sem refazer somas. A referência visual analisada não fixa quantidade, cores ou
tipo de gráfico no backend.

As séries permanecem dentro do snapshot editorial e da prévia administrativa.
Sua distribuição sem autenticação é feita somente pela API separada descrita
em [`PUBLIC_DISTRIBUTION_CONTRACT.md`](./PUBLIC_DISTRIBUTION_CONTRACT.md), nunca
por esta API administrativa.
