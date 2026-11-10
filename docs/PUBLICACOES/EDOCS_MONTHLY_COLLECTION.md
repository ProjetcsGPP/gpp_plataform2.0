# Coleta mensal E-Docs para apoio operacional

**Estado:** implementação inicial pertencente a `apps/pub_institucional`

**Consumidor atual:** processo operacional de PUBLICAÇÕES

**Não representa:** fonte aprovada para exposição pública; o contrato e a
classificação propostos ainda aguardam as aprovações registradas em
[`EDOCS_SOURCE_CONTRACT.md`](./EDOCS_SOURCE_CONTRACT.md) e
[`EDOCS_DATA_CLASSIFICATION.md`](./EDOCS_DATA_CLASSIFICATION.md)

## 1. Objetivo

Automatizar a coleta mensal de quantitativos já fornecidos pela API V2 do
E-Docs, preservar cada revisão e seus JSONs de resposta no banco e manter a
planilha apenas como exportação de apoio para a pessoa que executa o processo
atual.

O cliente E-Docs, os modelos, a reconciliação de patriarcas, os comandos e
as notificações pertencem ao contexto de PUBLICAÇÕES e, portanto, residem
em `apps/pub_institucional`. Apenas mecanismos comprovadamente reutilizáveis,
como o adaptador genérico do cofre de segredos, ficam em `common`. O `core`
permanece reservado a mecanismos profundos da plataforma.

A planilha existente `Localidade com cod + dados edocs.xlsx`, localizada fora
do repositório, foi lida somente como referência. Ela não é alterada pelo
comando. Colunas como localização, tamanho em disco, servidores treinados e
cálculos ambientais não são geradas porque não existem nos contratos
selecionados.

## 2. Métodos selecionados

| ID | Método e path | Uso |
|---|---|---|
| EDOC-05 | `GET /v2/agente/patriarcas` | Catálogo disponível e validação da seleção. |
| EDOC-01 | `GET /v2/processos/relatorio-quantitativos/mes/{mes}/ano/{ano}` | Total de processos por patriarca. |
| EDOC-02 | `GET /v2/processos/relatorio-quantitativos/{idPatriarca}/mes/{mes}/ano/{ano}` | Total de processos por organização do patriarca selecionado. |
| EDOC-03 | `GET /v2/documentos/relatorio-quantitativos/mes/{mes}/ano/{ano}` | Total de documentos e páginas por patriarca. |
| EDOC-04 | `GET /v2/documentos/relatorio-quantitativos/{idPatriarca}/mes/{mes}/ano/{ano}` | Total de documentos e páginas por organização do patriarca selecionado. |

Os schemas foram conferidos no Swagger oficial V2. Campos adicionais
retornados pela API são preservados nos JSONs e acrescentados ao fim das
colunas conhecidas da planilha.

## 3. Seleção de patriarcas

O catálogo definitivo possui o campo `coletar_detalhes`, que é a fonte
canônica para selecionar EDOC-01 a EDOC-04 na coleta persistente. A seleção é
congelada em `patriarcas_solicitados` ao criar cada revisão. A consulta
EDOC-05, por sua vez, sempre considera o catálogo remoto completo para detectar
novos registros, alterações e ausências.

O JSON versionado descrito abaixo permanece, nesta etapa, como entrada do
coletor mensal legado e como apoio à migração inicial. Ele não deve ser
atualizado automaticamente a partir de uma divergência ainda não aprovada.

A consulta controlada do catálogo é executada separadamente:

```bash
GPP_EDOCS_ENVIRONMENT=PRD \
GPP_EDOCS_CREDENTIALS_PROVIDER=openbao \
.venv/bin/python manage.py sincronizar_edocs_patriarcas
```

O comando registra a execução e as divergências, mas não altera o catálogo
definitivo. As decisões são aplicadas pelo serviço administrativo e serão
expostas ao frontend na etapa de API.

O arquivo canônico
[`config/edocs/patriarcas_disponiveis.json`](../../config/edocs/patriarcas_disponiveis.json)
contém `id`, `nome` e `COD_MUNIC` e vale para qualquer competência:

```json
[
  {
    "id": "b817315b-63ea-417e-b191-6ecbc42e56e4",
    "COD_MUNIC": 3201100,
    "nome": "MUNICÍPIO DE BOM JESUS DO NORTE"
  }
]
```

O identificador é a chave usada nas consultas. O nome facilita a revisão
humana e não substitui o nome retornado pelo E-Docs. IDs duplicados, inválidos
ou ausentes no EDOC-05 interrompem a execução antes dos relatórios detalhados.
`COD_MUNIC` é o código IBGE de sete dígitos e pode ser nulo para um patriarca
que não seja município, como `GOVES`. Os 24 códigos municipais foram validados
contra o
[Registro de Referência de Municípios](https://www.gov.br/conecta/catalogo/apis/registro-referencia-municipios)
e sua API oficial. A planilha manual foi apenas conferência; em caso de
divergência, prevalece o IBGE.
O comando preserva esse arquivo e consolida todos os patriarcas selecionados na
mesma planilha. Uma lista diferente somente é usada quando informada
explicitamente por `--patriarcas-config`; a troca de mês ou ano não altera a
seleção.

## 4. Saídas

### 4.1 Persistência mensal canônica

O fluxo administrativo grava no schema `publicacoes`:

| Entidade | Finalidade |
|---|---|
| `CompetenciaEdocs` | Identifica unicamente o par ano/mês. |
| `ColetaMensalEdocs` | Preserva uma revisão da competência e a seleção usada. |
| `FonteBrutaColetaMensalEdocs` | Preserva cada resposta JSON e seu SHA-256. |
| `ResultadoMensalPatriarcaEdocs` | Normaliza processos, documentos e páginas por patriarca. |
| `ResultadoMensalOrganizacaoEdocs` | Normaliza os mesmos totais por organização. |
| `EventoAuditoriaColetaMensalEdocs` | Registra solicitação, início, conclusão ou falha. |

Uma recoleta cria nova revisão. Nenhuma revisão anterior é atualizada ou
apagada, e os dados não são copiados fisicamente para o mês seguinte. A série
histórica é formada pela consulta das competências. O mês inicial da carga de
2024 ainda será informado e não está fixado no código.

O resultado por patriarca também congela `codigo_municipio` conforme o catálogo
no instante da execução. Os campos `municipio_implantado`,
`municipio_em_implantacao`, `municipio_manifestou_interesse` e
`municipio_implantado_sem_uso_edocs` permanecem no cadastro administrativo;
eles não são inferidos da API E-Docs.

### 4.2 Exportação operacional legada

Por padrão, o período é gravado em `var/edocs/AAAA-MM/`, ignorado pelo Git:

```text
var/edocs/AAAA-MM/
├── edocs_AAAA_MM.xlsx
├── patriarcas_catalogo_edocs.json
└── json/
    ├── edoc-05-patriarcas.json
    ├── edoc-01-processos-geral.json
    ├── edoc-03-documentos-geral.json
    ├── edoc-02-processos-ID.json
    └── edoc-04-documentos-ID.json
```

O diretório da competência e a pasta de JSONs usam permissão `0700`; os
arquivos são criados de forma atômica e não são gravados no repositório.

A planilha nova possui:

- `Parâmetros`: ambiente, competência e instante UTC da coleta;
- `Patriarcas`: IDs e nomes configurado/E-Docs;
- `Municípios`: `COD_MUNIC`, processos, documentos e páginas por patriarca;
- `Organizações`: `COD_MUNIC` e os mesmos quantitativos por organização;
- `Fontes`: métodos e paths efetivamente usados.

`config/edocs/patriarcas_disponiveis.json` é a entrada mantida pelo usuário;
`patriarcas_catalogo_edocs.json` é a fotografia normalizada do EDOC-05 em
cada competência. Assim, a coleta nunca sobrescreve a seleção manual.

As colunas `mes` e `ano` vêm dos parâmetros obrigatórios da própria consulta.
Nenhuma fórmula da planilha de referência é copiada.

## 5. Métricas existentes apenas no dashboard

O catálogo Swagger V2 não oferece relatório agregado equivalente a `TAMANHO
EM DISCO (GB)` nem a `PROCESSOS ENCERRADOS` do dashboard estatístico:

- `tamanhoBytes` existe no metadado de um documento individual, mas os
  relatórios quantitativos retornam somente documentos e páginas. Somar
  documentos individuais não reproduz comprovadamente a regra do dashboard e
  ainda depende de acesso e paginação;
- `POST /v2/processos/paginated-search` possui `somenteEncerrados` e retorna
  `count`, mas os filtros temporais documentados são de autuação e tramitação,
  não um intervalo de encerramento. Isso não comprova a quantidade encerrada
  dentro do mês exibida no dashboard.

Essas colunas permanecem ausentes até o E-Docs fornecer um endpoint/contrato
equivalente ou a regra do dashboard ser formalmente confirmada. Não serão
inferidas a partir de dados com semântica diferente.

## 6. Credenciais

O fluxo usa OAuth2 `client_credentials` no Acesso Cidadão com o escopo
`api-sigades-consultar`. `client_id`, `client_secret` e tokens nunca devem ser
versionados, registrados em log ou enviados por argumento de linha de comando.

Os valores comunicados em chat devem ser tratados como expostos. O código não
os reutiliza. Para DEV, o provisionador solicita os valores interativamente,
sem ecoar o segredo:

```bash
infra/publicacoes-dev/scripts/bootstrap-openbao.sh
.venv/bin/python infra/publicacoes-dev/scripts/provision_edocs_secret.py
```

São usados caminhos e AppRoles independentes:

| Perfil | Caminho KV v2 | AppRole DEV |
|---|---|---|
| HML | `gpp-shared/dev/edocs/hml` | `gpp-shared-edocs-hml-dev` |
| PRD | `gpp-shared/dev/edocs/prd` | `gpp-shared-edocs-prd-dev` |

## 7. Execução

Pela API administrativa, enviar `POST` para
`/api/pub-institucional/coletas-mensais-edocs/` com `ano` e `mes`. O backend
retorna `202`, e o Celery processa a revisão. O frontend acompanha o recurso
por HTTP; o WebSocket é apenas aviso para revalidação.

O comando abaixo continua gerando arquivos para a demanda operacional
específica. Ele não cria publicação e não substitui a coleta persistente:

Selecionar o ambiente e o cofre sem inserir segredo no `.env`:

```env
GPP_EDOCS_ENVIRONMENT=HML
GPP_EDOCS_CREDENTIALS_PROVIDER=openbao
```

Executar a competência desejada:

```bash
.venv/bin/python manage.py coletar_edocs_mensal \
  --mes 10 \
  --ano 2025
```

Para caminhos alternativos:

```bash
.venv/bin/python manage.py coletar_edocs_mensal \
  --mes 10 \
  --ano 2025 \
  --patriarcas-config /caminho/patriarcas.json \
  --output-dir /caminho/saida
```

O comando obtém um token somente em memória, repete uma consulta após `401`
com token novo, aplica timeout e retry limitado apenas aos `GET` idempotentes e
não inclui corpo remoto ou credenciais nas mensagens de erro.

## 8. Pendências antes de uso como fonte oficial

- nomear e registrar responsáveis e dono da informação;
- aprovar o contrato técnico e a classificação campo a campo já propostos;
- aprovar a lista canônica e o processo de alteração; a mesma lista vale para
  todas as competências até que uma nova versão seja deliberadamente mantida;
- confirmar diferenças operacionais entre treinamento e produção;
- definir tratamento formal de resposta vazia, indisponibilidade e correção;
- validar os quantitativos com a planilha/processo manual atual;
- aprovar agendamento, retenção dos JSONs e destino institucional dos arquivos.
