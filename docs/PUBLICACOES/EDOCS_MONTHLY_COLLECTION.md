# Coleta mensal E-Docs para apoio operacional

**Estado:** implementação inicial compartilhada em `apps/core`  
**Primeiro consumidor:** processo manual que antecede `pub_institucional`  
**Não representa:** contrato final de publicação, cálculo canônico ou fonte
aprovada para exposição pública

## 1. Objetivo

Automatizar a coleta mensal de quantitativos já fornecidos pela API V2 do
E-Docs, preservar os JSONs de resposta e gerar uma planilha de apoio para a
pessoa que executa a publicação atual.

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

- confirmar responsáveis e dono da informação;
- classificar cada campo e aprovar finalidade/retenção;
- decidir quais patriarcas integram cada competência;
- confirmar diferenças operacionais entre treinamento e produção;
- definir tratamento formal de resposta vazia, indisponibilidade e correção;
- validar os quantitativos com a planilha/processo manual atual;
- aprovar agendamento, retenção dos JSONs e destino institucional dos arquivos.
