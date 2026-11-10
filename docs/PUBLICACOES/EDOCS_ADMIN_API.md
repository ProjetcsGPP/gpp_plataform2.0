# API Administrativa do Catálogo E-Docs

**Status:** contrato inicial implementado  
**Aplicação IAM:** `PUB_INSTITUCIONAL`  
**Prefixo HTTP:** `/api/pub-institucional/`

## 1. Autenticação e autorização

A API usa a sessão compartilhada da plataforma no cookie
`gpp_session_PUB_INSTITUCIONAL`. O middleware resolve o contexto pelo prefixo
`pub-institucional`; não há autenticação ou autorização paralela.

| Operação | Permissão técnica |
|---|---|
| Listar/consultar patriarcas | `view_patriarcaedocs` |
| Alterar seleção de coleta | `selecionar_patriarcas_coleta` |
| Alterar indicador de município implantado sem uso do E-Docs | `alterar_indicador_municipio_sem_edocs` |
| Alterar código e indicadores municipais | `alterar_indicadores_municipais_edocs` |
| Listar/consultar coletas | `view_coletapatriarcasedocs` |
| Solicitar coleta | `solicitar_coleta_patriarcas_edocs` |
| Listar/consultar divergências | `view_divergenciapatriarcaedocs` |
| Decidir divergência | `revisar_patriarcas_edocs` |
| Listar/consultar auditoria | `view_eventoauditoriapatriarcaedocs` |
| Listar/consultar coletas mensais | `view_coletamensaledocs` |
| Solicitar coleta mensal | `solicitar_coleta_mensal_edocs` |
| Consultar resultados por patriarca | `view_resultadomensalpatriarcaedocs` |
| Consultar resultados por organização | `view_resultadomensalorganizacaoedocs` |
| Consultar metadados das fontes brutas | `view_fontebrutacoletamensaledocs` |
| Consultar auditoria mensal | `view_eventoauditoriacoletamensaledocs` |

Capabilities controlam a distribuição funcional. A autorização efetiva de
cada requisição continua sendo feita pelas permissões técnicas materializadas
da plataforma. Nenhum endpoint verifica o nome de uma role.

## 2. Endpoints

| Método e caminho | Finalidade |
|---|---|
| `GET /patriarcas/` | Lista o catálogo definitivo. |
| `GET /patriarcas/{id}/` | Consulta um patriarca definitivo. |
| `PATCH /patriarcas/{id}/selecao-coleta/` | Seleciona ou remove o patriarca das coletas detalhadas. |
| `PATCH /patriarcas/{id}/indicador-municipio-sem-edocs/` | Altera manualmente o indicador de município implantado sem uso do E-Docs. |
| `PATCH /patriarcas/{id}/indicadores-municipais/` | Altera parcialmente código IBGE e indicadores municipais manuais. |
| `GET /coletas/` | Lista execuções de consulta ao catálogo remoto. |
| `GET /coletas/{uuid}/` | Consulta uma execução. |
| `POST /coletas/` | Consulta o E-Docs e persiste comparação, divergências e auditoria. |
| `GET /divergencias/` | Lista divergências detectadas. |
| `GET /divergencias/{id}/` | Consulta evidências e decisões permitidas. |
| `POST /divergencias/{id}/decidir/` | Aplica decisão explícita ao catálogo definitivo. |
| `GET /auditoria/` | Lista eventos append-only. |
| `GET /auditoria/{id}/` | Consulta um evento de auditoria. |
| `GET /coletas-mensais-edocs/` | Lista revisões mensais persistidas. |
| `POST /coletas-mensais-edocs/` | Agenda a coleta de uma competência e retorna `202`. |
| `GET /resultados-mensais-patriarcas-edocs/` | Lista os quantitativos normalizados por patriarca. |
| `GET /resultados-mensais-organizacoes-edocs/` | Lista os quantitativos normalizados por organização. |
| `GET /fontes-brutas-coletas-mensais-edocs/` | Lista hashes e metadados das respostas preservadas. |
| `GET /auditoria-coletas-mensais-edocs/` | Lista eventos da execução mensal. |

Todos os caminhos da tabela são relativos a `/api/pub-institucional/`.
Listagens usam o envelope paginado padrão do projeto, com `count`, `next`,
`previous` e `results`.

## 3. Filtros e ordenação

- patriarcas: `ativo`, `coletar_detalhes`, `municipio_implantado`,
  `municipio_em_implantacao`, `municipio_manifestou_interesse`,
  `municipio_implantado_sem_uso_edocs`, `search` e `ordering`;
- coletas: `situacao` e `ordering`;
- divergências: `situacao`, `comparacao`, `coleta_id`, `patriarca_id` e
  `ordering`;
- auditoria: `tipo_evento`, `coleta_id`, `patriarca_id`, `divergencia_id` e
  `ordering`.
- coletas mensais: `ano`, `mes`, `situacao` e `ordering`;
- resultados mensais: `coleta_id`, `patriarca_id`, `search` e `ordering`;
- fontes brutas e auditoria mensal: `coleta_id` e `ordering`.

Booleanos aceitam `true`, `false`, `1` ou `0`. Identificadores e enums
inválidos retornam `400`, em vez de serem ignorados.

## 4. Mutações

### Seleção para coleta detalhada

```json
{
  "coletar_detalhes": true,
  "justificativa": "Município incluído na coleta mensal."
}
```

Patriarca inativo não pode ser selecionado. Mudança efetiva incrementa a
versão e gera `SELECAO_COLETA_ALTERADA` na auditoria.

### Município implantado sem uso do E-Docs

```json
{
  "municipio_implantado_sem_uso_edocs": true,
  "justificativa": "Implantação confirmada sem utilização do E-Docs."
}
```

O indicador é manual, não é inferido do catálogo remoto e não é alterado pela
sincronização E-Docs. Mudança efetiva incrementa a versão do patriarca e gera
`INDICADOR_SEM_EDOCS_ALTERADO`, preservando valores anterior e atual.

### Código e indicadores municipais

```json
{
  "codigo_municipio": 3201100,
  "municipio_implantado": true,
  "municipio_em_implantacao": false,
  "municipio_manifestou_interesse": true,
  "municipio_implantado_sem_uso_edocs": false,
  "justificativa": "Situação confirmada pelo gestor."
}
```

O `PATCH` é parcial: somente os campos enviados são alterados. Todos são
manuais, não vêm do EDOC-05 e não são recalculados pela coleta. `COD_MUNIC`
aceita sete dígitos ou `null`, é único quando preenchido e é congelado no
resultado de cada revisão mensal. Não foi imposta exclusividade entre os
indicadores porque a regra funcional de transição entre interesse,
implantação e implantação concluída ainda não foi formalizada.

Cada mudança efetiva incrementa `versao` e gera
`INDICADORES_MUNICIPAIS_ALTERADOS`, com valores anterior e atual, campos
alterados, justificativa, usuário e instante. A rota específica do indicador
“sem uso” foi preservada por compatibilidade.

### Solicitação de coleta

`POST /coletas/` não recebe payload. A operação consulta o catálogo remoto,
preserva as observações e retorna `201` com o recurso persistido. A criação do
recurso é bem-sucedida mesmo quando a integração termina em `FALHOU`; nesse
caso `situacao`, `codigo_erro` e `mensagem_erro` descrevem o resultado seguro.

A coleta nunca altera automaticamente o catálogo definitivo.

### Solicitação de coleta mensal

```json
{
  "ano": 2024,
  "mes": 9
}
```

A resposta `202` representa uma revisão `AGENDADA`. O worker consulta EDOC-05,
compara o catálogo sem aplicá-lo automaticamente e executa EDOC-01 a EDOC-04
para a seleção congelada no instante da solicitação. As situações possíveis
são `AGENDADA`, `EM_EXECUCAO`, `CONCLUIDA` e `FALHOU`.

Uma nova solicitação da mesma competência cria a revisão seguinte e nunca
sobrescreve resultados ou fontes anteriores. Duas revisões ativas da mesma
competência são rejeitadas com `409`. Totais ausentes em uma resposta são
persistidos como `null`, e não inferidos como zero.

As respostas JSON integrais ficam no banco restrito com SHA-256. A API
administrativa lista apenas seus metadados e hashes; o conteúdo bruto não é
transferido pelas listagens usuais. A coleta é independente de publicação e
nenhuma publicação é criada implicitamente.

### Decisão de divergência

```json
{
  "decisao": "ADICIONAR",
  "justificativa": "Cadastro confirmado junto à PRODEST.",
  "coletar_detalhes": true
}
```

Decisões possíveis dependem da comparação:

- `NOVO`: `ADICIONAR` ou `MANTER`;
- `ALTERADO`: `ATUALIZAR` ou `MANTER`;
- `AUSENTE`: `DESATIVAR` ou `MANTER`.

O campo `coletar_detalhes` é opcional. Conflito de versão, decisão repetida ou
existência de divergência mais recente retorna `409` com código estável
`conflito_catalogo_edocs`.

## 5. Ações autoritativas e tempo real

Patriarcas e divergências retornam `acoes_disponiveis`. Divergências também
retornam `decisoes_permitidas`. Esses campos consideram estado e permissão e
devem orientar os controles apresentados pelo frontend.

O WebSocket `/ws/pub-institucional/edocs/` anuncia solicitação, conclusão,
falha e decisões, inclusive para a coleta mensal.
Ele não substitui o estado HTTP: ao receber uma mensagem, o frontend deve
revalidar as chaves SWR correspondentes.

## 6. Erros

Erros seguem o envelope global:

```json
{
  "success": false,
  "status_code": 409,
  "errors": {
    "codigo": "conflito_catalogo_edocs",
    "detalhe": "A divergência já foi decidida."
  }
}
```

Mensagens remotas brutas, tokens e credenciais nunca são devolvidos.
