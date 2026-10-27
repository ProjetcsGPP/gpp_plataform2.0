# Pré-implementação obrigatória de `PUBLICACOES`

**Data:** 2026-10-26  
**Regra:** nenhum app, model, migration, endpoint, fixture ou teste sintético de
`PUBLICACOES` será criado antes da aprovação e comprovação deste checklist.

O dado do primeiro teste poderá ser sintético. A arquitetura, as fronteiras de
segurança e os componentes usados pelo teste deverão ser reais no ambiente de
desenvolvimento. HML e PRD serão definidos depois e poderão usar outros
produtos, desde que cumpram os contratos e testes fixados em DEV.

## 1. Decisões institucionais obrigatórias

| ID | Definir antes de implementar | Evidência exigida |
|---|---|---|
| PRE-001 | Nome funcional, gestor do produto, responsável técnico, segurança, infraestrutura e contatos de incidente. | Nomes ou equipes, canais e substitutos registrados. |
| PRE-002 | Primeiro caso de uso, dono da informação e conjunto piloto, mesmo que sua primeira representação seja sintética. | Contrato de fonte preenchido e aprovado, sem presumir regra da aplicação de origem. |
| PRE-003 | Classificação campo a campo: público, gerencial, restrito, dado pessoal e dado sensível. | Inventário de dados, finalidade, base de acesso, retenção e campos proibidos na distribuição. |
| PRE-004 | Topologia de `DEV`, fronteiras e caminhos browser/SSR/worker; requisitos portáveis para ambientes futuros. | Diagrama de DEV aprovado e contratos que HML/PRD deverão satisfazer. |
| PRE-005 | PostgreSQL on-premises já usado em DEV, schema `publicacoes`, usuário técnico, privilégios e procedimento de backup/restore. | Evidência da instância real; a sandbox Docker não substitui sua validação. RPO/RTO ficam para o ambiente alvo. |
| PRE-006 | Object storage e política de bucket/container privado, versionamento, criptografia, retenção e descarte. | Serviço escolhido, acessos provisionados e teste de leitura/escrita/negação. |
| PRE-007 | Antivírus/sandbox, quarentena, estados de análise e comportamento em indisponibilidade. | Scanner escolhido e teste com arquivo limpo e arquivo de teste EICAR; falha fechada comprovada. |
| PRE-008 | Secrets manager, identidade de workload e recuperação em DEV; rotação programada, revogação e acesso emergencial completos ficam para HML/PRD. | Serviço escolhido; aplicação obtém segredo sem persistir valor no repositório, banco ou log; guia operacional de DEV aprovado. |
| PRE-009 | Reverse proxy de DEV e contrato futuro de gateway/CDN: TLS, limites, rate limit, headers confiáveis, logs e purge. | Proxy local e testes de cache público/privado e limites; CDN não é instalada em DEV. |
| PRE-010 | Política de egress para cada tipo de conector: destinos, DNS, proxy, IPs proibidos, redirects, timeout e volume. | Regra de rede e teste que permite destino aprovado e bloqueia redes privadas/metadata. |
| PRE-011 | Formato de logs, métricas, traces, correlação e redação de dados; destino futuro desacoplado. | Logs locais estruturados e testes de redação; plataforma central será escolhida por ambiente. |
| PRE-012 | Categorias de SLA, RPO, RTO, retenção, resposta a incidentes e continuidade, sem fixar valores de PRD em DEV. | Procedimentos locais de restore/indisponibilidade e responsáveis pelas decisões futuras. |
| PRE-013 | Autenticação de usuários, autorização de gestor/administrador e estratégia M2M futura. | Matriz de acesso aprovada; decisões PUB-005 a PUB-010 e provedor M2M registrado. |
| PRE-014 | Contratos de API, cache, SSR/CSR, versionamento, erros, idempotência e concorrência. | ADRs e schemas iniciais aprovados, inclusive estado sem publicação vigente. |
| PRE-015 | Cadeia de fornecimento de DEV/CI: imagens fixadas, SBOM, análise de dependências e rollback local. | Compose e pipeline local/CI reproduzíveis; registry e promoção serão definidos antes de HML. |
| PRE-016 | Serviços de controle, contratos de decisão e workflow de ordem do gestor. | ADR-0006 aprovado; autoridade, justificativa, registro e execução especificados na suíte comum. |

## 2. Componentes a provisionar

Não se instala um produto antes de `PRE-004` a `PRE-012` identificarem o
serviço de desenvolvimento. Após a escolha, devem existir em `DEV`:

1. PostgreSQL on-premises existente, isolado por credenciais e schema, com
   backup e restore validados na instância real; sandbox local é opcional;
2. Redis para fila/coordenação e Memcached conforme a arquitetura compartilhada;
3. workers Celery separados do processo web;
4. object storage privado com área de quarentena e área aprovada;
5. scanner antimalware acessível somente pelo worker de análise;
6. secrets manager acessado por identidade da carga de trabalho;
7. reverse proxy com TLS local e implementação do contrato HTTP obrigatório;
8. controle de egress no nível de rede, não apenas validação na aplicação;
9. logs estruturados, métricas e traces em formato exportável;
10. pipeline local/CI para produzir artefato e SBOM reproduzíveis.

CDN não será instalada nem escolhida para o teste sintético. A política de
cache e a interface de purge precisam estar decididas porque afetam o contrato
HTTP; o provedor será escolhido no gate do ambiente que usar CDN.

## 3. Dependências que poderão ser instaladas após a escolha

O repositório já possui clientes para PostgreSQL, Redis, Memcached e Celery.
Ainda não possui cliente de object storage nem integração de antivírus,
secrets manager ou observabilidade distribuída.

As dependências exatas serão adicionadas somente depois dos ADRs de produto:

- cliente S3/Blob compatível com o storage selecionado;
- cliente do secrets manager selecionado, preferencialmente por identidade de
  workload e sem segredo de bootstrap permanente;
- integração com o daemon/API antimalware selecionado;
- SDK de telemetria baseado em padrão exportável e desacoplado do coletor;
- integração de purge do gateway/CDN selecionado.

O produto local não precisa ser o produto de produção. Ele deverá implementar
a mesma interface portável, e suas diferenças e limitações serão documentadas.
Cada ambiente futuro repetirá os testes contra o produto nele escolhido.

## 4. Ordem obrigatória de execução

1. Nomear responsáveis e aprovar o caso piloto e a classificação dos dados.
2. Levantar com infraestrutura os serviços já disponíveis e seus responsáveis.
3. Aprovar a topologia e os ADRs de banco, storage, AV, secrets, gateway,
   egress, observabilidade, backup, deploy e serviços de controle.
4. Definir os contratos que SLA, RPO, RTO, retenção e resposta a incidentes
   deverão cumprir quando cada ambiente alvo for criado.
5. Provisionar `DEV`, sem credenciais ou dados de produção.
6. Instalar nos repositórios apenas os clientes dos produtos aprovados e fixar
   suas versões.
7. Configurar CI/CD, análise de dependências, migração e rollback.
8. Executar o preflight técnico abaixo e anexar as evidências à matriz.
9. Só então criar `apps/publicacoes`, seu schema e o primeiro teste sintético.

HML e PRD possuem gates próprios e não são pressupostos pelo gate de DEV.

## 5. Preflight técnico obrigatório

O gate somente passa quando todos os resultados forem reproduzíveis:

- conexão autorizada e negação de acesso indevido ao schema PostgreSQL;
- backup, perda simulada e restore dentro do RPO/RTO aprovado;
- upload privado, quarentena, scan limpo, rejeição EICAR e indisponibilidade do
  scanner com falha fechada;
- suspeita antimalware permanece em quarentena; ordem justificada do gestor
  preserva o achado original e vale somente para o mesmo hash;
- obtenção e substituição explícita de segredo sem exposição em banco, log ou
  resposta; rotação periódica será testada no gate de HML/PRD;
- egress permitido somente para host aprovado e bloqueado para loopback,
  redes privadas, link-local e serviço de metadata;
- TLS, rate limit, limite de corpo e headers de cache aplicados pelo gateway;
- purge e separação entre cache público, autenticado e preview;
- logs redigidos, correlação de request/job e alerta recebido;
- deploy em HML e rollback para o artefato anterior;
- testes existentes de autenticação, cookie, CSRF e autorização ainda passando.
- adapters do ambiente aprovados pela mesma suíte de contratos de segurança;
- workflow de ordem rejeita replay e mudança de hash, exige justificativa,
  registra o resultado e executa sem segunda aprovação.

## 6. Resultado do gate

O checklist não é aprovado por intenção ou por documentação isolada. Cada item
deverá ter responsável, decisão, evidência e data na matriz compartilhada.
Enquanto um item permanecer pendente, `PUBLICACOES` permanece em planejamento:
inclusive seu teste sintético não será criado.

## 7. Evidência atual de DEV

Em 2026-10-26 foram comprovados o preflight funcional, o backup/restore
criptografado e a regressão backend completa. A suíte teve 1.138 aprovações,
1 teste ignorado e cobertura de 87,55%. SBOMs e relatórios Trivy também foram
gerados sem supressão automática.

O primeiro uso real do contrato de segredos também foi aplicado ao
`carga_org_lot`: a credencial CargaRH PRD saiu do `.env`, passou a ser lida por
AppRole exclusiva e ficou separada do perfil HML. Isso comprova o adapter e a
negação entre ambientes, mas não encerra `PRE-008` para os demais segredos do
backend. DEV não possui rotação periódica; esse contrato será definido no gate
de HML/PRD.

O gate permanece aberto pelos itens descritos em
[`SECURITY_EVIDENCE_2026-10-26.md`](./SECURITY_EVIDENCE_2026-10-26.md): achados
altos/críticos, validação da instância PostgreSQL on-premises, egress de rede,
observabilidade e decisões institucionais `PRE-001` a `PRE-003`.
