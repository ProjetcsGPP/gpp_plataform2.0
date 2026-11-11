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
