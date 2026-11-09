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
| Listar/consultar coletas | `view_coletapatriarcasedocs` |
| Solicitar coleta | `solicitar_coleta_patriarcas_edocs` |
| Listar/consultar divergências | `view_divergenciapatriarcaedocs` |
| Decidir divergência | `revisar_patriarcas_edocs` |
| Listar/consultar auditoria | `view_eventoauditoriapatriarcaedocs` |

Capabilities controlam a distribuição funcional. A autorização efetiva de
cada requisição continua sendo feita pelas permissões técnicas materializadas
da plataforma. Nenhum endpoint verifica o nome de uma role.

## 2. Endpoints

| Método e caminho | Finalidade |
|---|---|
| `GET /patriarcas/` | Lista o catálogo definitivo. |
| `GET /patriarcas/{id}/` | Consulta um patriarca definitivo. |
| `PATCH /patriarcas/{id}/selecao-coleta/` | Seleciona ou remove o patriarca das coletas detalhadas. |
| `GET /coletas/` | Lista execuções de consulta ao catálogo remoto. |
| `GET /coletas/{uuid}/` | Consulta uma execução. |
| `POST /coletas/` | Consulta o E-Docs e persiste comparação, divergências e auditoria. |
| `GET /divergencias/` | Lista divergências detectadas. |
| `GET /divergencias/{id}/` | Consulta evidências e decisões permitidas. |
| `POST /divergencias/{id}/decidir/` | Aplica decisão explícita ao catálogo definitivo. |
| `GET /auditoria/` | Lista eventos append-only. |
| `GET /auditoria/{id}/` | Consulta um evento de auditoria. |

Todos os caminhos da tabela são relativos a `/api/pub-institucional/`.
Listagens usam o envelope paginado padrão do projeto, com `count`, `next`,
`previous` e `results`.

## 3. Filtros e ordenação

- patriarcas: `ativo`, `coletar_detalhes`, `search` e `ordering`;
- coletas: `situacao` e `ordering`;
- divergências: `situacao`, `comparacao`, `coleta_id`, `patriarca_id` e
  `ordering`;
- auditoria: `tipo_evento`, `coleta_id`, `patriarca_id`, `divergencia_id` e
  `ordering`.

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

### Solicitação de coleta

`POST /coletas/` não recebe payload. A operação consulta o catálogo remoto,
preserva as observações e retorna `201` com o recurso persistido. A criação do
recurso é bem-sucedida mesmo quando a integração termina em `FALHOU`; nesse
caso `situacao`, `codigo_erro` e `mensagem_erro` descrevem o resultado seguro.

A coleta nunca altera automaticamente o catálogo definitivo.

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

O WebSocket `/ws/pub-institucional/edocs/` anuncia conclusão, falha e decisões.
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
