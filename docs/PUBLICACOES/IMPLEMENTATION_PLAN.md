# Plano de Implementação por Fases

**Quantidade proposta:** 8 fases, numeradas de 0 a 7  
**Regra:** uma fase só encerra quando seus gates forem comprovados

## Visão geral

| Fase | Tema | Resultado principal |
|---|---|---|
| 0 | Descoberta e segurança de base | Riscos críticos conhecidos, decisões e ambiente inventariados |
| 1 | Fundação da aplicação | App, schema, IAM, auditoria e modelos-base |
| 2 | Publicação manual vertical | Uma publicação criada, validada e congelada sem integração |
| 3 | API pública e novo Portal | Conteúdo publicado no dashboard e login em modal |
| 4 | Integração entre aplicações | Outbox, providers, snapshots e reconciliação |
| 5 | APIs externas e planilhas | Conectores, quarentena e processamento seguro |
| 6 | Consumidores da distribuição | Cadastro, credenciais, escopos, quotas e observabilidade |
| 7 | Homologação e entrada em operação | Segurança, carga, recuperação, treinamento e go-live |

## Fase 0 — Descoberta e segurança de base

### Fazer

- validar e corrigir CSRF nas views DRF autenticadas;
- validar expiração, revogação e usuário ativo nas sessões customizadas;
- implementar throttling específico de login e remover enumeração de usuário;
- inventariar proxy, gateway, DNS, TLS, object storage, secrets e backups;
- elaborar threat model e classificação preliminar de dados;
- escolher o conjunto de dados piloto sem definir regras de fontes não ouvidas;
- aplicar a decisão de que o mesmo gestor poderá preparar e publicar;
- manter para `PORTAL_ADMIN` o acesso administrativo global da plataforma, sem
  permitir exceções às regras de domínio;
- definir SLA, RPO, RTO e responsáveis;
- registrar ADRs das decisões aprovadas.

### Não fazer ainda

- criar conectores externos;
- cadastrar segredos reais;
- expor novos endpoints públicos;
- automatizar publicação;
- modificar regras de aplicações de origem.

### Gates

- testes negativos de CSRF, sessão expirada/inativa e brute force passando;
- diagrama de fluxo e inventário de dados aprovados;
- riscos P0 sem pendência aberta;
- ADRs de preparação/publicação e bypass administrativo aprovados;
- plano de rollback aprovado.

## Fase 1 — Fundação da aplicação

### Backend

- criar `apps/publicacoes` e schema `publicacoes`;
- registrar `Aplicacao` com código `PUBLICACOES`;
- criar role `GESTOR_PUBLICACOES` e permissões técnicas;
- criar capabilities e menus por seed idempotente;
- implementar models iniciais de fonte, snapshot, publicação e histórico;
- usar `AuditableModel` e serviços transacionais;
- criar estados e invariantes de workflow;
- documentar OpenAPI administrativo.

### Frontend

- adicionar `PUBLICACOES` ao `AppContext` e configuração compartilhada;
- criar manifesto/navegação e layout usando infraestrutura existente;
- criar telas administrativas mínimas sem mecanismo HTTP paralelo;
- implementar guards baseados em permissões.

### Infraestrutura e testes

- migration e rollback testados em PostgreSQL;
- testes de models, serviços, permissões, IDOR e auditoria;
- nenhuma credencial real em fixture, log ou documentação.

### Gates

- `manage.py check` e `makemigrations --check` aprovados;
- testes backend e frontend aprovados;
- OpenAPI sem erro;
- matriz role/permissão revisada;
- usuário sem role não acessa a aplicação.

## Fase 2 — Publicação manual vertical

### Fazer

- cadastrar conteúdo manual controlado para o piloto;
- criar rascunho e relatório de validação;
- avançar pelo workflow aprovado;
- congelar snapshot publicado;
- criar nova versão para correção;
- substituir ou revogar sem exclusão física;
- registrar justificativa e histórico completo;
- oferecer pré-visualização interna.

### Gates

- publicação publicada não pode ser alterada;
- correção preserva versão anterior;
- todas as transições são transacionais e auditadas;
- concorrência não produz duas versões vigentes incompatíveis;
- exportação permite reproduzir a publicação.

## Fase 3 — API pública e novo Portal

### Backend

- implementar API pública `v1` sobre snapshots publicados;
- adicionar versionamento, schema version, ETag e paginação;
- aplicar cache, limites de resposta e throttling;
- impedir exposição de rascunhos, artefatos e campos não públicos;
- produzir contrato e exemplos OpenAPI específicos.

### Frontend

- transformar `/portal` em página pública;
- renderizar publicação vigente via contrato canônico;
- extrair `LoginForm` e apresentá-lo em modal;
- preservar `/portal/login` por redirecionamento compatível;
- após login, exibir aplicações autorizadas e conteúdo reorganizado;
- manter Axios, SWR, `appContext`, theme e navegação existentes.

### Gates

- testes de vazamento de campos e estados não publicados;
- acessibilidade e responsividade validadas;
- cache não mistura resposta pública e autenticada;
- comportamento sem publicação vigente definido;
- teste de carga do endpoint público aprovado;
- rollback para tela anterior documentado.

## Fase 4 — Integração entre aplicações

### Fazer

- implementar outbox transacional compartilhado;
- implementar dispatcher idempotente com retry e dead-letter;
- criar registry e contrato de `PublicationSourceProvider`;
- selecionar uma única integração piloto após validação com sua equipe;
- obter snapshot por DTO versionado;
- implementar reconciliação incremental por cursor e hash;
- criar testes de contrato produtor/consumidor;
- tratar correção, substituição e indisponibilidade.

### Observação obrigatória

Eventos e transições citados em discussões anteriores são exemplos. O contrato
do piloto será escrito e aprovado separadamente antes de alterar a aplicação de
origem.

### Gates

- falha entre commit e despacho não perde evento;
- reprocessamento não duplica snapshot ou publicação candidata;
- versão/hash divergente é detectado;
- aplicação de origem funciona quando `PUBLICACOES` está indisponível;
- reconciliação recupera entrega simuladamente perdida;
- nenhuma consulta direta a tabela de outro domínio.

## Fase 5 — APIs externas e planilhas

### APIs externas

- criar tipos de conectores aprovados;
- aplicar allowlist e proteção SSRF;
- usar TLS, timeout, retry limitado e circuit breaker;
- armazenar segredo em mecanismo externo ao model de negócio;
- limitar paginação, volume, duração e custo;
- redigir erros e logs sem credenciais ou payload sensível.

### Planilhas

- upload autenticado para quarentena;
- limitar tamanho, extensão, tipo real e expansão descompactada;
- gerar nome interno e hash;
- executar antivírus/sandbox conforme infraestrutura escolhida;
- processar em worker isolado com limites de CPU e memória;
- preservar original e relatório de validação;
- impedir fórmulas/links ativos no conteúdo distribuído.

### Gates

- testes de SSRF, redirect, DNS e timeout;
- testes de arquivo adulterado, macro, ZIP/XML bomb e tamanho;
- indisponibilidade externa não bloqueia requests web;
- segredo não aparece em banco, API, logs ou eventos;
- reprocessamento preserva idempotência e evidências.

## Fase 6 — Consumidores da distribuição

### Fazer

- cadastrar consumidor interno ou externo;
- definir responsável, ambiente, finalidade e validade;
- aprovar escopos e quotas;
- emitir credencial mostrando o segredo uma única vez;
- armazenar somente hash e prefixo identificador;
- implementar rotação, sobreposição e revogação;
- registrar uso e último acesso;
- aplicar limites por consumidor;
- criar procedimento de comprometimento de credencial.

### Gates

- credencial revogada deixa de funcionar imediatamente;
- rotação não exige indisponibilidade;
- consumidor não acessa recurso fora do escopo;
- logs permitem atribuir chamadas sem registrar segredo;
- contratos públicos e autenticados permanecem separados.

## Fase 7 — Homologação e entrada em operação

### Validar

- pentest ou revisão independente proporcional ao risco;
- SAST, dependências, segredos e configuração de produção;
- carga, cache, filas e degradação controlada;
- backup, restauração e disaster recovery;
- expiração, rotação e revogação de credenciais;
- observabilidade, alertas e runbooks;
- LGPD, transparência, retenção e resposta a incidente;
- treinamento de gestores e administradores;
- piloto acompanhado e rollback.

### Gates de go-live

- nenhum risco P0/P1 sem aceite formal;
- restauração comprovada;
- alertas testados;
- runbook e contatos publicados internamente;
- gestor piloto treinado;
- contratos versionados e monitorados;
- aceite funcional, técnico, segurança e operação.

## Definition of Done transversal

Cada entrega deve incluir:

- regra/invariante documentada;
- migration reversível quando aplicável;
- testes positivos, negativos, autorização e concorrência;
- OpenAPI e exemplos atualizados;
- logs sem dados sensíveis;
- métricas e alertas proporcionais;
- documentação operacional;
- plano de rollback;
- evidência de validação no PR.
