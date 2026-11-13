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
| Consultar localidades do IBGE | `view_municipioedocs` |

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
| `POST /coletas-mensais-edocs/` | Solicita a coleta de uma competência e retorna `202`. |
| `POST /coletas-mensais-edocs/{uuid}/reencaminhar/` | Reencaminha uma solicitação que ainda não começou. |
| `GET /resultados-mensais-patriarcas-edocs/` | Lista os quantitativos normalizados por patriarca. |
| `GET /resultados-mensais-patriarcas-edocs/totais/` | Consolida todos os municípios de uma revisão mensal. |
| `GET /resultados-mensais-patriarcas-edocs/totais-historicos/` | Consolida resultados entre competências e anos. |
| `GET /resultados-mensais-organizacoes-edocs/` | Lista os quantitativos normalizados por organização. |
| `GET /fontes-brutas-coletas-mensais-edocs/` | Lista hashes e metadados das respostas preservadas. |
| `GET /auditoria-coletas-mensais-edocs/` | Lista eventos da execução mensal. |
| `GET /implantacoes-edocs/` | Lista a primeira implantação observada por patriarca. |
| `GET /ibge/configuracao/` | Informa a UF padrão configurada no backend. |
| `GET /ibge/estados/` | Lista os estados obtidos da API oficial do IBGE. |
| `GET /ibge/estados/{codigo_uf}/municipios/` | Lista os municípios da UF informada. |
| `GET /ibge/municipios/` | Lista, por nome, apenas municípios da UF padrão ainda não cadastrados. |

Todos os caminhos da tabela são relativos a `/api/pub-institucional/`.
Listagens usam o envelope paginado padrão do projeto, com `count`, `next`,
`previous` e `results`.

### 2.1 Cadastro municipal independente

Municípios que ainda não existem no catálogo oficial usam recursos próprios:

| Método e caminho | Finalidade |
|---|---|
| `GET /municipios-edocs/` | Lista municípios e suas vigências. |
| `POST /municipios-edocs/` | Cadastra município por código IBGE, sem UUID externo fictício. |
| `GET /municipios-edocs/{id}/` | Consulta cadastro, patriarca associado e histórico. |
| `PATCH /municipios-edocs/{id}/situacao/` | Abre uma nova situação a partir de uma competência. |
| `PATCH /municipios-edocs/{id}/cadastro/` | Corrige código IBGE ou nome com controle de versão. |
| `GET /auditoria-municipios-edocs/` | Consulta eventos auditáveis do cadastro municipal. |

A inclusão exige código IBGE de município do Espírito Santo (`32xxxxx`), nome,
situação, ano/mês inicial e justificativa. As situações aceitas são
`SEM_DADOS`, `MANIFESTOU_INTERESSE`,
`EM_IMPLANTACAO` e `IMPLANTADO_SEM_USO_EDOCS`. Cada alteração encerra a
vigência anterior no mês precedente. O DTO informa `patriarca_edocs: null`
enquanto não houver patriarca real associado ao mesmo código IBGE.

Quando uma coleta oficial detectar a primeira atividade positiva, o backend
cria o município caso necessário, associa o patriarca pelo código IBGE,
encerra a situação manual anterior e passa a retornar
`IMPLANTADO_COM_USO_EDOCS` com origem `API_OFICIAL_EDOCS`. Essa transição gera
auditoria e não exige confirmação nem preenchimento manual pelo usuário. Se o
patriarca ainda não possuir código IBGE válido, a coleta é preservada, mas a
associação ao mapa continuará pendente até a correção do código.

Os campos municipais ainda expostos em `/patriarcas/` são compatibilidade
legada. O cadastro acima é a fonte canônica para novos registros e para o mapa.

### 2.2 Localidades oficiais do IBGE

O navegador não acessa diretamente a API externa. O frontend de Publicações
consulta inicialmente `GET /api/pub-institucional/ibge/municipios/`; o backend
usa `IBGE_UF_PADRAO=32`, consulta o serviço oficial, normaliza o contrato e
mantém códigos e nomes municipais em cache sem expiração. Assim, a consulta
externa ocorre somente no primeiro acesso após uma invalidação, reinício do
serviço de cache ou evicção. O valor padrão também é devolvido por
`/ibge/configuracao/`, mas não precisa ser codificado no frontend.

A rota simplificada `/ibge/municipios/` compara o catálogo em cache com
`municipio_edocs` a cada requisição. Sua resposta contém somente `nome` e
`codigo_ibge`, nessa ordem, exclui inclusive cadastros inativos e é ordenada
alfabeticamente pelo nome. Portanto, um município recém-cadastrado deixa de
aparecer imediatamente, sem invalidar nem consultar novamente o IBGE.

Os nomes persistidos podem ser auditados e reconciliados novamente com
`python manage.py sincronizar_nomes_municipios_ibge`. Sem argumentos, o
comando apenas lista divergências; `--aplicar` atualiza pelo serviço de domínio,
incrementa a versão e cria `CADASTRO_CORRIGIDO` para cada município alterado.

O cliente HTTP e o cache ficam em `common`, pois podem atender outras
aplicações. A exposição autenticada permanece em `pub_institucional`, seguindo
o contexto, a sessão e a permissão técnica da aplicação. As rotas genéricas de
estados e municípios por UF ficam disponíveis para evolução futura sem obrigar
uma consulta prévia no fluxo atual.

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
- implantações observadas: `ano`, `mes`, `search` e `ordering`.

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

### Município implantado sem uso do E-Docs (compatibilidade legada)

```json
{
  "municipio_implantado_sem_uso_edocs": true,
  "ano_inicio": 2024,
  "mes_inicio": 6,
  "justificativa": "Implantação confirmada sem utilização do E-Docs."
}
```

O indicador é manual, não é inferido do catálogo remoto e não é alterado pela
sincronização E-Docs. A ativação exige a primeira competência em que a situação
deve valer; a desativação limpa essa vigência. Registros legados já marcados,
mas ainda sem competência, continuam preservados e não entram em mapas
históricos até serem confirmados pelo gestor. Novas decisões devem usar
`/municipios-edocs/{id}/situacao/`. Mudança efetiva nesta rota antiga incrementa a
versão do patriarca e gera `INDICADOR_SEM_EDOCS_ALTERADO`, preservando valores
anterior e atual.

### Código e indicadores municipais (compatibilidade legada)

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

O `PATCH` é parcial e foi preservado para o frontend anterior; somente os
campos enviados são alterados. Todos são
manuais, não vêm do EDOC-05 e não são recalculados pela coleta. `COD_MUNIC`
aceita sete dígitos ou `null`, é único quando preenchido e é congelado no
resultado de cada revisão mensal. Esses campos não alimentam mais o mapa
`IMPLANTACAO_EDOCS_V2`. Não foi imposta exclusividade entre os
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

A resposta `202` representa uma revisão `SOLICITADA`. O worker consulta EDOC-05,
compara o catálogo sem aplicá-lo automaticamente e executa EDOC-01 a EDOC-04
para a seleção congelada no instante da solicitação. As situações possíveis
são `SOLICITADA`, `EXECUTANDO`, `SUCESSO` e `ERRO`.

Uma nova solicitação da mesma competência cria a revisão seguinte e nunca
sobrescreve resultados ou fontes anteriores. Duas revisões ativas da mesma
competência são rejeitadas com `409`. Totais ausentes em uma resposta são
persistidos como `null`, e não inferidos como zero.

O resultado por patriarca também retorna `versao_calculo` e os campos
`economia_papel_kg`, `gases_poluentes_kg`, `economia_papel_reais`,
`economia_insumos_reais`, `economia_impressao_reais`,
`economia_total_reais`, `economia_agua_m3` e `arvores_salvas`. Esses valores
são calculados e persistidos no processamento da revisão, não pelo frontend.
Para os cálculos derivados, exclusivamente, totais ausentes equivalem a zero,
como ocorre nas fórmulas da planilha de referência.

Para a consulta consolidada, enviar obrigatoriamente `coleta_id` para
`GET /resultados-mensais-patriarcas-edocs/totais/`. O backend soma todos os
resultados da revisão, independentemente da paginação usada na tabela, e
retorna `quantidade_municipios`, os três quantitativos de origem e os oito
indicadores calculados. O frontend não deve recalcular o total a partir da
página visível.

Os quatro somatórios históricos usam o mesmo endpoint, variando os filtros:

| Escopo | Parâmetros |
|---|---|
| Somatório por ano | `ano=AAAA` |
| Somatório de todos os anos | sem parâmetros |
| Somatório anual de um município | `ano=AAAA&patriarca_id=ID` |
| Somatório de todos os anos de um município | `patriarca_id=ID` |

Para cada competência mensal, o backend considera somente a revisão de maior
número com situação `SUCESSO`. Revisões anteriores e revisões em situação
`SOLICITADA`, `EXECUTANDO` ou `ERRO` não participam do somatório. A resposta
informa `quantidade_competencias`, `quantidade_municipios`, `versoes_calculo`,
o ano e município aplicados e todos os quantitativos e indicadores somados.

As respostas JSON integrais ficam no banco restrito com SHA-256. A API
administrativa lista apenas seus metadados e hashes; o conteúdo bruto não é
transferido pelas listagens usuais. A coleta é independente de publicação e
nenhuma publicação é criada implicitamente.

Enquanto a situação for `SOLICITADA`, a resposta contém
`acoes_disponiveis: ["reencaminhar"]` para usuários com a permissão de
solicitar. O reencaminhamento reutiliza a mesma revisão e não duplica a coleta.
Solicitações antigas também são reencaminhadas pelo Celery Beat. Por padrão, o
monitor executa a cada 60 segundos e considera recuperável uma solicitação sem
início há pelo menos 120 segundos. Esses intervalos são configuráveis por
`GPP_EDOCS_RECOVERY_INTERVAL_SECONDS` e
`GPP_EDOCS_REQUEST_STALE_SECONDS`.

Mensagens duplicadas são idempotentes: o worker somente inicia a coleta se o
estado persistido ainda for `SOLICITADA`. Um registro `EXECUTANDO`, `SUCESSO`
ou `ERRO` não é reiniciado pela mesma mensagem.

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
