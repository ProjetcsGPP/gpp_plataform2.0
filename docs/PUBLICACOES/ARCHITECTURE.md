# Arquitetura da Aplicação `PUBLICACOES`

**Status:** proposta controlada  
**Escopo:** backend, frontend, integrações e infraestrutura

## 1. Limites de responsabilidade

### Aplicação de origem

Cada aplicação de origem permanece responsável por:

- suas regras e estados de negócio;
- identificar versões canônicas dos próprios dados;
- expor um snapshot versionado por contrato;
- classificar os campos que podem sair do domínio;
- informar alteração relevante por mecanismo acordado;
- manter evidências que permitam reproduzir o snapshot.

Este documento não determina quais ações ou estados de uma aplicação são
relevantes. Isso será decidido por fonte.

### Aplicação `PUBLICACOES`

Será responsável por:

- registrar fontes e contratos;
- receber notificações ou executar coletas agendadas;
- armazenar artefatos e snapshots com rastreabilidade;
- validar e normalizar conteúdo recebido;
- executar cálculos próprios da publicação e cruzamentos entre fontes;
- preparar, revisar, publicar, substituir e revogar publicações;
- oferecer API pública e API autenticada de distribuição;
- controlar consumidores, escopos, quotas e credenciais;
- fornecer o conteúdo do dashboard público do Portal.

### Portal

O Portal será responsável por:

- apresentar a publicação vigente;
- renderizar indicadores, gráficos, textos e metadados do contrato público;
- abrir o login em modal;
- após autenticação, apresentar as aplicações permitidas ao usuário;
- não recalcular regras de negócio ou indicadores canônicos.

## 2. Arquitetura lógica

```text
Fontes internas        APIs externas        Planilhas
      │                      │                  │
      └──────────────┬───────┴──────────────────┘
                     ▼
          Integração, coleta e quarentena
                     │
                     ▼
          Snapshot bruto e rastreabilidade
                     │
                     ▼
       Validação, normalização e cálculos
                     │
                     ▼
             Publicação candidata
                     │
             revisão e aprovação
                     │
                     ▼
            Publicação imutável
              │              │
              ▼              ▼
       Dashboard público   API de distribuição
```

## 3. Integração com aplicações internas

O padrão inicial será híbrido:

1. A aplicação de origem conclui sua própria transação.
2. Na mesma transação, grava um evento em outbox.
3. Um worker entrega a notificação após o commit.
4. `PUBLICACOES` processa o evento de forma idempotente.
5. `PUBLICACOES` solicita ao provedor da origem o snapshot da versão indicada.
6. Uma reconciliação periódica compara cursores, versões e hashes.

O evento transporta referência e metadados mínimos, não o conjunto completo de
dados. Exemplo não normativo:

```json
{
  "event_id": "uuid",
  "event_type": "dominio.recurso.alterado",
  "source": "CODIGO_DA_APLICACAO",
  "aggregate_type": "tipo_do_recurso",
  "aggregate_id": "identificador",
  "source_version": "versao",
  "schema_version": 1,
  "occurred_at": "2026-10-23T14:30:00-03:00"
}
```

Enquanto origem e consumidor estiverem no mesmo Django, a obtenção do snapshot
será feita por interface Python e DTO, não por chamada HTTP e nunca por consulta
direta às tabelas alheias.

Interface conceitual:

```python
class PublicationSourceProvider(Protocol):
    source_code: str

    def get_snapshot(
        self,
        resource_type: str,
        resource_id: str,
        source_version: str,
    ) -> PublicationSourceSnapshot: ...

    def list_changes(
        self,
        cursor: str | None,
    ) -> SourceChangesPage: ...
```

Cada contrato de fonte deverá documentar separadamente:

- responsável funcional e técnico;
- eventos disponíveis;
- significado de cada evento;
- campos do snapshot;
- classificação de segurança;
- versionamento e compatibilidade;
- cursor de reconciliação;
- volume e frequência esperados;
- tratamento de correção, substituição e indisponibilidade.

## 4. Integrações externas

Ordem de preferência:

1. notificação assinada seguida de consulta autenticada;
2. consulta incremental agendada por cursor;
3. importação manual de arquivo em quarentena.

URLs externas não serão livremente informadas a cada execução. O cadastro de uma
fonte selecionará conectores e destinos aprovados. Credenciais ficarão fora do
banco de negócio e nunca serão devolvidas ao frontend.

## 5. Modelo conceitual

| Entidade | Responsabilidade |
|---|---|
| `FonteDados` | Identidade, proprietário, classificação e situação da fonte |
| `ContratoFonte` | Schema, versão, compatibilidade e método de integração |
| `ExecucaoColeta` | Tentativa, duração, correlação, resultado e métricas |
| `ArtefatoOrigem` | Evidência bruta imutável, hash, tamanho e estado de varredura |
| `SnapshotFonte` | Versão normalizada e rastreável recebida de uma fonte |
| `DefinicaoIndicador` | Metadados e responsabilidade de um indicador |
| `ResultadoIndicador` | Valor, dimensões, período, algoritmo e proveniência |
| `Publicacao` | Agregado versionado sujeito ao workflow editorial |
| `ItemPublicacao` | Conteúdo congelado de uma publicação |
| `HistoricoPublicacao` | Transições, autor, data e justificativa |
| `ConsumidorAPI` | Identidade de sistema, contatos, ambiente e situação |
| `CredencialConsumidor` | Hash, prefixo, validade, escopos e revogação |
| `AssinaturaDistribuicao` | Recursos e versões acessíveis ao consumidor |
| `EventoOutbox` | Entrega confiável e idempotente de notificações |

## 6. Workflow da publicação

Proposta inicial:

```text
RASCUNHO
  → EM_VALIDACAO
  → AGUARDANDO_PUBLICACAO
  → PUBLICADA
  → SUBSTITUIDA

Saídas excepcionais: REJEITADA, CANCELADA, REVOGADA
```

Após `PUBLICADA`, conteúdo e metadados distribuídos tornam-se imutáveis. Uma
correção cria nova versão e referencia a anterior. Revogação não apaga a
evidência histórica.

## 7. Perfis, capabilities e permissões

### Perfil funcional inicial

`GESTOR_PUBLICACOES` será o único perfil funcional de negócio na primeira
versão. Isso reduz complexidade operacional sem transformar a role em fonte de
autorização dentro do frontend.

O perfil receberá permissões técnicas granulares, entre elas, conforme os models
efetivamente criados:

- consultar, cadastrar e alterar fontes;
- consultar execuções e solicitar nova coleta;
- consultar artefatos e relatórios de validação;
- criar e alterar rascunhos;
- validar, publicar, substituir e revogar;
- gerir consumidores, escopos e rotação de credenciais.

Nomes definitivos seguirão as permissões Django `view_*`, `add_*`, `change_*` e
`delete_*`, complementadas por permissões de ação como `publish_publicacao` e
`rotate_credencial`. Componentes frontend consultarão permissões, nunca nomes de
roles.

### Separação de funções

Com uma única role, um gestor poderá preparar e publicar se o workflow aprovado
permitir. Se a governança exigir duas pessoas, a regra poderá impedir que o
mesmo usuário prepare e publique, embora ambos possuam
`GESTOR_PUBLICACOES`. Portanto, segregação entre pessoas não exige por si só
uma segunda role. O modelo e o histórico deverão suportar essa política sem
presumi-la na primeira entrega.

### Atores que não são perfis funcionais

- visitante público: acesso somente ao contrato público;
- consumidor de API: identidade de máquina, sem `UserRole`;
- administrador da plataforma: administra IAM e cadastro técnico; o alcance do
  bypass atual de `PORTAL_ADMIN` sobre ações editoriais será validado no threat
  model antes da implementação.

## 8. Contratos de distribuição

Versão inicial proposta:

```text
GET /api/public/v1/dashboard/
GET /api/public/v1/publicacoes/
GET /api/public/v1/publicacoes/{uuid}/
GET /api/public/v1/indicadores/{codigo}/series/
GET /api/distribuicao/v1/...
```

Toda resposta pública informará `publication_id`, versão, competência,
`schema_version`, instante de publicação e proveniência permitida. Publicações
específicas serão imutáveis; o endpoint `dashboard` poderá apontar para a última
publicação vigente. Serão usados `ETag`, `Last-Modified`, paginação e limites de
resposta.

## 9. Regras de dependência

- `PUBLICACOES` não importa models de origem para calcular regras do domínio.
- Provedores devolvem DTOs versionados e publicamente classificáveis.
- Eventos WebSocket ou filas são notificações; o estado persistido é canônico.
- Frontend não duplica cálculos do backend.
- Sessão humana e credencial máquina-a-máquina não são intercambiáveis.
- Capability controla distribuição funcional; permissão técnica autoriza ação.
