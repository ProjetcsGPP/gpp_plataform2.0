# Serviços e contratos de controles de segurança

**Status:** decisão arquitetural inicial  
**Data:** 2026-10-26  
**Escopo:** DEV e contrato obrigatório para ambientes futuros

## 1. Princípio

Cada camada de segurança será exposta por um serviço com contrato próprio,
veredicto explícito, versão de política e evidência. A implementação poderá ser
substituída sem alterar o workflow consumidor.

“Serviço” significa uma fronteira lógica e testável. Não implica que todo
controle será um microserviço HTTP:

- políticas e orquestração podem começar como serviços Python isolados;
- operações pesadas ou privilegiadas devem executar em processos/containers
  separados;
- integrações com storage, scanner e secrets manager usam adapters;
- nenhuma implementação concreta será chamada diretamente pela regra de
  negócio.

## 2. Contrato comum de decisão

Todos os controles devem aceitar uma requisição equivalente a:

```json
{
  "request_id": "uuid",
  "correlation_id": "uuid",
  "control": "FILE_MALWARE_SCAN",
  "operation": "PROCESS_UPLOAD",
  "subject": {
    "type": "user|service|worker",
    "id": "opaque-id"
  },
  "resource": {
    "type": "artifact|endpoint|publication|secret",
    "id": "uuid-or-code",
    "version": "opaque-version",
    "sha256": "hex-when-applicable"
  },
  "context": {},
  "requested_at": "RFC-3339"
}
```

E devolver:

```json
{
  "decision_id": "uuid",
  "verdict": "ALLOW|DENY|REVIEW|RETRY",
  "reason_code": "stable_machine_code",
  "policy_id": "policy-code",
  "policy_version": "immutable-version",
  "constraints": {},
  "evidence_refs": ["opaque-evidence-id"],
  "evaluated_at": "RFC-3339",
  "valid_until": null
}
```

Regras comuns:

- `ALLOW` autoriza somente a operação, recurso, versão/hash e prazo avaliados;
- `DENY` bloqueia o fluxo automático, mas pode ser objeto de ordem expressa do
  gestor;
- `REVIEW` aguarda decisão do gestor e não autoriza prosseguir sozinho;
- `RETRY` indica indisponibilidade ou resultado inconclusivo e mantém falha
  fechada;
- códigos de motivo são estáveis; mensagens humanas não dirigem lógica;
- evidências podem conter metadados, nunca segredo ou conteúdo restrito
  desnecessário;
- mudança de conteúdo, hash, destino, ator, operação ou política invalida a
  decisão anterior;
- timeout ou resposta inválida do controle equivale a `RETRY`, nunca `ALLOW`.

## 3. Catálogo inicial de serviços

| Serviço lógico | Responsabilidade | Entrada principal | Saída/efeito |
|---|---|---|---|
| `AuthorizationDecisionService` | Autorizar ação humana ou de sistema | ator, app, ação, recurso | veredicto e escopo efetivo |
| `FileIntakePolicyService` | Validar tamanho, nome interno, tipo, hash e limites de arquivo | metadados e referência de quarentena | aceita, nega ou pede revisão |
| `MalwareScanService` | Produzir achados antimalware sem expor o arquivo ao processo web | objeto imutável em quarentena | achados, engine, assinaturas e veredicto preliminar |
| `ArchiveSafetyService` | Detectar macro, estrutura inválida, ZIP/XML bomb e expansão excessiva | referência/hash e limites | relatório estrutural e veredicto |
| `ContentValidationService` | Validar schema, fórmulas, links, células e regras do contrato da fonte | artefato aprovado estruturalmente | relatório versionado |
| `DataClassificationService` | Aplicar classificação e allowlist campo a campo | snapshot e contrato de classificação | campos aceitos, redigidos ou negados |
| `ExternalDestinationPolicyService` | Validar host, DNS, IP conectado, TLS, porta e redirects | conector cadastrado e destino resolvido | destino e limites autorizados |
| `ExternalResponsePolicyService` | Limitar status, tamanho, tipo, paginação e conteúdo recebido | metadados da resposta e stream limitado | aceita, rejeita ou interrompe leitura |
| `SecretLeaseService` | Fornecer credencial temporária para operação específica | identidade do workload e secret ref | lease opaco/temporário, nunca persistência funcional |
| `PublicationDisclosureService` | Impedir que campo/estado não público chegue à distribuição | publicação congelada e schema público | DTO público autorizado e evidência |
| `AuditEvidenceService` | Persistir decisões, transições e exceções de forma append-only | evento redigido e correlação | referência de evidência confirmada |
| `SecurityOrderService` | Registrar e aplicar a ordem justificada do gestor | decisão de controle, recurso exato e justificativa | aprovação/rejeição e ordem de execução auditada |
| `SecurityWorkflowService` | Orquestrar controles e estados sem ocultar resultados | operação, decisões e exceções | próxima ação permitida e estado canônico |

## 4. Workflow seguro de arquivos

```text
RECEBIDO
  → EM_QUARENTENA
  → INTAKE_VALIDADO
  → ESTRUTURA_VALIDADA
  → ANALISE_ANTIMALWARE
  → ANTIMALWARE_APROVADO
  → CONTEUDO_VALIDADO
  → CLASSIFICADO
  → APROVADO_PARA_PROCESSAMENTO
  → PROCESSADO
```

Saídas negativas ou temporárias:

- `REJEITADO_INTAKE`;
- `REJEITADO_ESTRUTURA`;
- `SUSPEITO_ANTIMALWARE`;
- `BLOQUEADO_ANTIMALWARE`;
- `LIBERADO_POR_ORDEM_GESTOR`;
- `REJEITADO_CONTEUDO`;
- `BLOQUEADO_CLASSIFICACAO`;
- `AGUARDANDO_REANALISE`;
- `AGUARDANDO_EXCECAO`;
- `EXCECAO_EXPIRADA`.

O processo web apenas recebe o stream e grava no storage de quarentena. Ele não
abre planilha, arquivo compactado ou documento. Hash e tamanho são calculados
durante a gravação. Workers posteriores consomem a referência imutável.

Um arquivo nunca salta diretamente de quarentena para publicação. Se o gestor
ordenar o prosseguimento, a aplicação registra a ordem e retoma o workflow para
o mesmo hash. O resultado original permanece no histórico.

### Resultado antimalware e falso positivo

Um achado de uma ferramenta não equivale, isoladamente, a malware confirmado.
O scanner devolve, além do contrato comum:

- engine e versão;
- versão/data das assinaturas;
- instante e duração do scan;
- identificadores dos achados;
- categoria e confiança disponíveis;
- hash efetivamente analisado;
- limitações ou erros da análise.

Mapeamento inicial:

| Resultado técnico | Veredicto | Efeito |
|---|---|---|
| Limpo | `ALLOW` preliminar | Avança apenas para os demais controles. |
| Suspeito ou achado passível de falso positivo | `REVIEW` | Mantém quarentena e aguarda decisão do gestor. |
| Inconclusivo, timeout ou engine indisponível | `RETRY` | Mantém quarentena e agenda nova tentativa. |
| Achado bloqueante segundo a ferramenta/política | `DENY` | Bloqueia automaticamente e aguarda eventual ordem do gestor. |

O gestor não precisa produzir laudo, segundo scan, avaliação de risco ou
controle compensatório. Basta estar autorizado, selecionar a decisão e o
arquivo exatos e registrar justificativa não vazia. Se aprovar, o estado passa
a `LIBERADO_POR_ORDEM_GESTOR` e a ordem deve ser executada.

A aplicação não afirma tecnicamente que houve falso positivo. Ela registra o
achado da ferramenta e, separadamente, a ordem do gestor. Se a justificativa
declarar falso positivo, isso será preservado como declaração do gestor. A
liberação vale apenas para o mesmo hash; arquivo alterado passa novamente por
todo o workflow.

## 5. Workflow seguro de API externa

```text
CONECTOR_SELECIONADO
  → DESTINO_VALIDADO
  → DNS_IP_VALIDADO
  → SEGREDO_CONCEDIDO
  → REQUISICAO_LIMITADA
  → RESPOSTA_LIMITADA
  → PAYLOAD_VALIDADO
  → SNAPSHOT_ACEITO
```

Regras:

- não existe URL livre fornecida no momento da execução;
- o conector referencia destino previamente cadastrado;
- DNS e IP são validados novamente no instante da conexão;
- redes privadas, loopback, link-local e metadata permanecem bloqueadas;
- redirects são desabilitados ou cada salto repete toda a validação;
- TLS não tem opção de desativar verificação;
- segredo é obtido somente depois da aprovação do destino;
- resposta é lida em streaming com tempo e tamanho máximos;
- falha não produz snapshot parcial válido.

## 6. Ordem justificada do gestor

O gestor é a autoridade funcional. Uma decisão automatizada informa e bloqueia
o fluxo padrão, mas não substitui a decisão do gestor. Quando ele ordenar o
prosseguimento, a aplicação deve registrar e executar.

### Workflow

```text
CONTROLE_BLOQUEOU_OU_PEDIU_REVISAO
  → AGUARDANDO_DECISAO_GESTOR
  → GESTOR_APROVOU | GESTOR_REJEITOU
  → EXECUCAO_SOLICITADA
  → EXECUTADA | FALHOU
```

### Campos obrigatórios

- `decision_id` original;
- controle e versão de política;
- operação exata;
- recurso, versão e hash;
- gestor que decidiu;
- justificativa não vazia;
- data e hora da decisão;
- resultado da execução, inclusive mensagem redigida em caso de falha.

O registro aprovado será consumido de forma atômica pela operação exata. Não
haverá parâmetro oculto como `skip_validation`, `ignore_security` ou
`force=true`: a ordem será uma entidade de domínio visível e auditada.

### Casos alcançados pela ordem

| Caso | Condições mínimas |
|---|---|
| Scanner indisponível, suspeita ou achado | Gestor identifica o arquivo/hash, justifica e ordena processar. |
| Divergência de extensão/MIME ou estrutura | Gestor identifica o alerta, justifica e ordena prosseguir. |
| Limite de tamanho/tempo de API | Gestor identifica o conector/operação, justifica e ordena executar. |
| Destino ainda não aprovado automaticamente | Gestor identifica o destino exato, justifica e ordena acessar. |
| Regra de qualidade/classificação | Gestor identifica campos e publicação, justifica e ordena continuar. |
| Reprocessamento manual | Gestor identifica a execução anterior, justifica e ordena repetir. |

### Requisitos para reconhecer a ordem

- o ator está autenticado e reconhecido como gestor ou administrador global;
- a justificativa não está vazia;
- o objeto, operação e, quando aplicável, hash estão identificados;
- a ordem e seu resultado são gravados antes/depois da execução;
- registros anteriores não são apagados nem reescritos.

Esses requisitos não julgam a decisão do gestor; apenas comprovam que a ordem
existiu, a quem se referia e qual foi seu resultado. Se a execução falhar por
razão técnica, a aplicação registra a falha em vez de declarar sucesso.

### Auditoria e logs técnicos

A justificativa integral será preservada na trilha de auditoria com acesso
restrito. Logs técnicos e observabilidade registrarão apenas `order_id`, ator,
controle, referência/hash do alvo, timestamps e resultado redigido. Eles não
duplicarão justificativa, segredo ou conteúdo do arquivo. Assim todas as ações
ficam rastreáveis sem espalhar informação sensível por múltiplos logs.

## 7. Autoridade

A aplicação continuará com um único perfil funcional inicial. O
`GESTOR_PUBLICACOES` receberá uma única permissão técnica de ação,
`approve_security_order`. Não haverá segundo aprovador, laudo obrigatório,
avaliação de risco ou responsabilidades adicionais.

`PORTAL_ADMIN` mantém o acesso global já decidido, mas deve registrar a mesma
justificativa e ordem antes da execução.

## 8. Testes de contrato obrigatórios

Cada implementação deverá passar pelo mesmo conjunto de testes:

- todos os veredictos e códigos previstos;
- arquivo limpo, EICAR, suspeita simulada e scanner indisponível;
- ordem justificada preserva o achado original e só libera exatamente o mesmo
  hash;
- timeout, indisponibilidade e resposta inválida resultam em falha fechada;
- mudança de hash, recurso ou operação exige nova ordem;
- replay acidental da mesma ordem é rejeitado;
- ordem é persistida antes e resultado depois da ação;
- logs não contêm segredo nem conteúdo restrito;
- adapters alternativos produzem a mesma semântica;
- workflow não avança quando um controle obrigatório está ausente;
- ausência de gestor autorizado ou justificativa bloqueia a ordem;
- aprovação válida provoca tentativa real de execução, sem etapa de aprovação
  adicional escondida.

Esses testes constituem o contrato. Uma nova ferramenta somente será aceita se
passar por eles sem condições especiais dentro do domínio.
