# Contrato de distribuição pública de Publicações Institucionais

**Versão do contrato:** 1.0  
**Situação:** backend implementado; integração e apresentação frontend pendentes  
**Decisões relacionadas:** `PUB-002`, `PUB-014`, `PUB-017`, `PUB-023`,
`PUB-024` e `PUB-025`

## 1. Fronteira obrigatória

A API pública não reutiliza o router, as views nem os serializers da API
administrativa.

| Contrato | Base | Autenticação | Cache |
|---|---|---|---|
| Administrativo | `/api/pub-institucional/` | sessão e permissões técnicas | `private, no-store` para preview |
| Público | `/api/public/v1/publicacoes-institucionais/` | nenhuma sessão | cache público conforme `PUB-014` |

A implementação pública ficará em pacote próprio dentro do domínio
`pub_institucional`, com `urls`, views, serializers, projeções e testes próprios.
Ela usará `AllowAny`, `authentication_classes = []` e throttle público dedicado.
Cookies ou cabeçalhos de sessão não poderão alterar a representação e a resposta
não enviará `Vary: Cookie`.

O serviço editorial continua responsável por calcular e congelar conteúdo. A
camada pública somente projeta uma publicação imutável por uma allowlist. Ela
não consulta coletas operacionais para completar uma resposta já publicada.

## 2. Responsabilidade do backend

O backend entrega dados independentes de componente visual:

- identificação, versão e competência da publicação;
- seções congeladas e sua ordem editorial;
- indicadores com código estável, título, unidade e precisão;
- séries mensais com valor da competência, valor acumulado quando aplicável e
  proveniência pública por ponto;
- consolidados históricos por município, já ordenados para rankings, sem impor
  quantidade de barras ou componente visual;
- mapas congelados, categorias, legenda e alternativa textual/tabular;
- data de publicação e versão do schema público.

Para E-Docs, cada série é um fluxo mensal e fornece `valor` e
`valor_acumulado`. Para E-Flow, os totais representam o estoque observado no
snapshot vigente; portanto, não existe soma acumulada entre competências.

Antes da publicação, a composição histórica segue esta precedência:

1. resultado congelado da publicação válida da competência e da mesma visão;
2. na ausência de publicação, última coleta E-Docs bem-sucedida ou snapshot
   E-Flow vigente;
3. sem fonte válida, ponto explícito com valor nulo e origem `SEM_DADOS`.

A publicação congela a série resultante. Uma consulta pública nunca refaz essa
precedência em tempo de leitura.

No mapa `IMPLANTACAO_EDOCS`, cada item usa `codigo_ibge` com sete dígitos para
associação ao GeoJSON. A regra `IMPLANTACAO_EDOCS_V2` expõe as categorias
`IMPLANTADO_COM_USO_EDOCS`, `IMPLANTADO_SEM_USO_EDOCS`, `EM_IMPLANTACAO`,
`MANIFESTOU_INTERESSE` e `SEM_DADOS`, acompanhadas da legenda congelada. O uso
observado pela API oficial prevalece sobre a situação manual vigente. Município
sem patriarca oficial pode participar normalmente por seu cadastro IBGE; não é
criado UUID externo fictício. Município
ausente do cadastro administrativo também integra `municipios`, usando nome e
código oficiais do IBGE, categoria `SEM_DADOS` e texto alternativo. A resposta
informa ainda `codigo_uf` e `quantidade_municipios`, permitindo que o frontend
componha o mapa completo sem outra chamada de dados.

Os conjuntos E-Docs usados pelos gráficos e rankings também expõem
`nome_municipio` junto de `codigo_municipio`. O frontend não deve usar
`nome_patriarca` como rótulo municipal nem cruzar o ranking com o mapa para
descobrir o nome.

A primeira atividade positiva observada encerra automaticamente a situação
manual anterior e produz evento de auditoria municipal. A API pública apenas
projeta o mapa já congelado; o frontend não solicita confirmação dessa mudança.

## 3. Responsabilidade do frontend

O frontend decide, sem alterar os valores canônicos:

- tipo de gráfico, mapa, cartão ou tabela;
- composição em slides, ordem visual, duração e reprodução;
- responsividade, transições e comportamento em tela cheia;
- apresentação acessível dos estados HTTP e dos dados alternativos;
- navegadores suportados e meta de acessibilidade de `PUB-025`.

O frontend não soma pontos, recalcula percentuais, muda categorias do mapa nem
substitui valores ausentes por zero.

## 4. Schema neutro de série histórica

Cada seção poderá expor zero ou mais séries no formato:

```json
{
  "codigo": "TOTAL_PAGINAS",
  "titulo": "Páginas",
  "periodicidade": "MENSAL",
  "natureza": "FLUXO_MENSAL",
  "unidade": "páginas",
  "precisao": 0,
  "serie_completa": true,
  "pontos": [
    {
      "competencia": "2024-06",
      "valor": "100",
      "valor_acumulado": "100",
      "proveniencia": {
        "tipo": "PUBLICACAO"
      }
    }
  ]
}
```

Valores decimais são strings em base dez para não perder precisão. Ausência de
dado é `null`, nunca zero inferido. Identificadores internos de coleta,
usuários, justificativas, hashes de fontes e trilhas administrativas não fazem
parte da projeção pública.

## 5. Recursos públicos versionados

Os recursos estão implementados fora do router administrativo:

```text
GET /api/public/v1/publicacoes-institucionais/vigente/
GET /api/public/v1/publicacoes-institucionais/{uuid}/
GET /api/public/v1/publicacoes-institucionais/{uuid}/series/
GET /api/public/v1/publicacoes-institucionais/
```

`vigente/` aponta para a publicação não revogada de maior competência. Dentro
da mesma competência, prevalece a versão publicada mais recentemente. Se a
última competência publicada tiver sido revogada e não substituída, o ponteiro
não recua silenciosamente para uma competência anterior.

A listagem histórica contém somente representações autorizadas que foram
publicadas e não foram revogadas. Uma versão substituída pode permanecer no
histórico imutável, mas nunca volta a ser vigente.

## 6. Estados públicos (`PUB-024`)

| Situação | HTTP | Código estável | Regra |
|---|---:|---|---|
| Nenhuma publicação disponível | 404 | `PUBLICACAO_NAO_DISPONIVEL` | não retornar preview ou coleta |
| Publicação específica inexistente | 404 | `PUBLICACAO_NAO_ENCONTRADA` | resposta sem detalhes internos |
| Publicação revogada | 410 | `PUBLICACAO_REVOGADA` | não reutilizar como vigente nem em cache |
| Limite público excedido | 429 | `LIMITE_PUBLICO_EXCEDIDO` | enviar `Retry-After` |
| Falha temporária | 503 | `PUBLICACAO_TEMPORARIAMENTE_INDISPONIVEL` | não trocar por conteúdo administrativo |

Offline é um estado do cliente e será tratado pelo frontend. O backend fornece
ETag, `Last-Modified` e códigos estáveis. A invalidação de publicação,
substituição ou revogação deve retirar imediatamente o ponteiro público
anterior; conteúdo revogado não pode ser usado como fallback vigente.

## 7. Critérios de não vazamento

Testes contratuais deverão demonstrar que a API pública não expõe:

- usuário, role, capability ou sessão;
- IDs e payloads brutos de coleta;
- justificativas e eventos administrativos;
- hashes operacionais ou mensagens internas de erro;
- rascunhos, conteúdo em validação, preview ou publicação revogada;
- campos acrescentados futuramente sem inclusão explícita na allowlist.
