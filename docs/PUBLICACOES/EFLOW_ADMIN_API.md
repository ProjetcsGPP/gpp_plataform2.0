# API administrativa da coleta E-Flow

**Base:** `/api/pub-institucional/`  
**Autenticação:** sessão da aplicação `PUB_INSTITUCIONAL`  
**Fonte:** exportação CSV manual do E-Flow Admin

## 1. Decisão de persistência

Cada envio cria um snapshot independente. O backend preserva o CSV original,
seu SHA-256, as linhas normalizadas, o resultado da validação, os indicadores e
a trilha de auditoria. Uma nova importação não sobrescreve a anterior e nenhuma
coleta cria ou modifica publicação automaticamente.

O arquivo deve ser UTF-8, usar `;` e possuir exatamente as colunas `ID`, `Nome`,
`Versão`, `Público-alvo`, `Patriarca`, `Órgão` e `Setor`. O limite padrão é 10 MB
e 100.000 registros, configurável por `GPP_EFLOW_CSV_MAX_BYTES` e
`GPP_EFLOW_CSV_MAX_ROWS`.

## 2. Endpoints

| Método | Rota | Permissão | Finalidade |
|---|---|---|---|
| `POST` | `coletas-eflow/` | `importar_coleta_eflow` | Envia `arquivo` como multipart e processa o snapshot |
| `GET` | `coletas-eflow/` | `view_coletaeflow` | Lista coletas e indicadores congelados |
| `GET` | `coletas-eflow/{uuid}/` | `view_coletaeflow` | Consulta uma coleta |
| `GET` | `definicoes-eflow/` | `view_definicaofluxoeflow` | Lista linhas normalizadas |
| `GET` | `definicoes-eflow/{id}/` | `view_definicaofluxoeflow` | Consulta uma linha |
| `GET` | `resultados-eflow/` | `view_resultadocalculoeflow` | Lista resultados por coleta e perfil |
| `GET` | `resultados-eflow/{id}/` | `view_resultadocalculoeflow` | Consulta um resultado calculado |
| `GET` | `preferencias-eflow/minha/` | `view_preferenciaexibicaoeflow` | Consulta ou inicializa a preferência do usuário |
| `PATCH` | `preferencias-eflow/minha/` | `alterar_preferencia_exibicao_eflow` | Altera a preferência sem justificativa |
| `GET` | `auditoria-preferencias-eflow/` | `view_eventoauditoriapreferenciaeflow` | Consulta a própria trilha de preferência |
| `GET` | `auditoria-eflow/` | `view_eventoauditoriaeflow` | Lista eventos imutáveis |

O `POST` retorna `201` com `situacao=CONCLUIDA` quando o conteúdo é aceito. Uma
falha descoberta após a preservação do arquivo também retorna a coleta criada,
com `situacao=FALHOU`, `codigo_erro` e `mensagem_erro`. Erros de transporte,
extensão ou tamanho que impedem criar o snapshot retornam `400`.

## 3. Filtros e ordenação

- coletas: `situacao` e `ordering` por `iniciada_em`, `concluida_em` ou
  `situacao`;
- definições: `coleta_id`, `patriarca_id`, `publico_alvo`, `search` e
  `ordering` por `nome`, `orgao`, `setor` ou `publico_alvo`;
- resultados: `coleta_id`, `perfil` e `ordering` por `calculado_em` ou
  `perfil`;
- auditoria: `coleta_id`, `tipo_evento` e `ordering` por `criado_em` ou
  `tipo_evento`.

Listas usam a paginação comum da plataforma. Filtros inválidos recebem `400`.

## 3.1 Preferência individual de exibição

Cada usuário possui uma preferência independente. No primeiro acesso ela é
inicializada como `CONSOLIDADO_PUBLICACAO`. A alteração aceita somente:

```json
{
  "perfil_preferido": "COMPLETO_TECNICO"
}
```

Não há justificativa. Inicialização e mudança efetiva geram log operacional e
evento append-only com perfil anterior, perfil atual, ator e horário. Repetir o
mesmo valor é idempotente e não cria evento artificial.

A preferência define apenas qual resultado a interface abre primeiro. Os dois
resultados continuam disponíveis e não são recalculados, removidos ou
sobrescritos. Ela também não seleciona conteúdo de uma publicação futura.

## 4. Perfis e indicadores canônicos

Cada coleta concluída possui exatamente dois resultados fechados:

- `COMPLETO_TECNICO`: órgãos por `Patriarca + Órgão`, setores por
  `Patriarca + Órgão + Setor`, cinco maiores com `Outros`, todos os
  públicos-alvo e percentuais sobre o total de fluxos;
- `CONSOLIDADO_PUBLICACAO`: órgãos e setores por nome global, somente os cinco
  maiores sem `Outros`, percentuais sobre os cinco exibidos e distribuição
  restrita a Cidadão, Órgão e Patriarca, com denominador sobre essas categorias.

Não existe edição campo a campo dessas regras nesta versão. Se as regras forem
aprimoradas futuramente, resultados históricos não deverão ser reescritos.

A resposta da coleta contém:

- `quantidade_fluxos`;
- `quantidade_orgaos_participantes`;
- `quantidade_setores_ativos`;
- `orgaos_maior_quantidade_fluxos`, com os cinco maiores e a fatia `Outros`;
- `distribuicao_publico_alvo`.

Os campos diretos da coleta preservam a compatibilidade e correspondem a
`COMPLETO_TECNICO`. O campo `resultados_calculo` contém os dois perfis. O mesmo
conteúdo pode ser consultado de forma paginada em `resultados-eflow/`.

Percentuais são calculados no backend, arredondados para duas casas e enviados
como texto decimal com ponto. O frontend apenas os apresenta. A expressão
“Setores Ativos” significa, neste recorte, setores distintos representados no
CSV, pois a fonte não fornece um campo de situação do setor.

## 5. Reconciliação com patriarcas

A sigla inicial da coluna `Patriarca` deve identificar exatamente um registro
em `patriarca_edocs`. Sigla ausente ou ambígua reprova todo o snapshot; não há
vínculo parcial nem criação automática de patriarca. A forma textual recebida é
preservada junto com a referência normalizada.

## 6. Operação por linha de comando

Após aplicar as migrações e reconciliar o seed:

```bash
.venv/bin/python manage.py importar_eflow_csv /caminho/exportacao.csv
.venv/bin/python manage.py gerar_resultados_eflow
```

O comando usa o mesmo serviço da API e registra o ator técnico
`comando:importar_eflow_csv`.

`gerar_resultados_eflow` cria somente perfis ausentes para snapshots antigos;
resultados existentes não são recalculados nem sobrescritos.
