# Inventário de Infraestrutura — Fase 0

**Data da verificação inicial:** 2026-10-26
**Última reconfirmação documental:** 2026-11-03
**Escopo:** evidências presentes nos repositórios backend e frontend  
**Matriz:** `PUB-020` e `PUB-022`

Este inventário registra somente o que pôde ser comprovado no código e na
configuração versionada. Ausência de evidência não será interpretada como
infraestrutura disponível.

## Componentes comprovados

| Área | Estado atual comprovado | Impacto em `PUBLICACOES` |
|---|---|---|
| Banco | PostgreSQL on-premises multi-schema, configurado nos settings, com router próprio | Será necessário validar a instância real e adicionar schema `publicacoes`, search path, migration e rollback. |
| Cache backend | Memcached, timeout padrão de 300 segundos | Pode apoiar cache interno; não substitui o contrato HTTP/CDN do ADR-0005. |
| Processamento assíncrono | Celery com Redis e Celery Beat | Base disponível para coleta, validação, outbox e reconciliação. |
| Tempo real | Django Channels com Redis | Disponível para progresso administrativo; não é fonte canônica. |
| Sessão | Cookies separados por aplicação, CSRF e sessão no banco | `PUBLICACOES` deverá receber contexto e cookie próprios na Fase 1. |
| TLS Django | Redirect HTTPS, HSTS e proxy SSL configurados em produção | Depende de proxy confiável e valores corretos no ambiente real. |
| CORS/CSRF | Allowlists por ambiente; CSRF de produção obrigatório | Origem pública e administrativa precisa ser registrada no deploy. |
| Segredos atuais | `.env` lido por `django-environ` | Não há evidência de secrets manager institucional ou rotação automatizada. |
| Logs | Arquivos rotativos locais e console | Não há evidência de centralização, retenção institucional ou alertas. |
| Qualidade/segurança CI | CodeQL, Gitleaks, Trivy, Flake8, Pylint e pytest | Base útil; faltam testes específicos de upload, SSRF, cache e restore. |
| Proxy frontend local | Rewrites Next.js para `localhost:8000` | É apenas desenvolvimento; origem/gateway de produção não está definida. |
| Domínios backend | Mapa atual para Portal, Ações e Carga | Não existe domínio/host registrado para `PUBLICACOES` ou API pública. |

## Sandbox auxiliar versionada

Desde a verificação inicial, `infra/publicacoes-dev` passou a conter uma
sandbox opcional com PostgreSQL isolado, Redis, Memcached, SeaweedFS/S3,
ClamAV, OpenBao e Nginx/TLS, além de scripts de preflight, backup/restore,
SBOM/scan e testes de negação. Esses componentes demonstram contratos locais;
não comprovam serviços institucionais, o PostgreSQL on-premises, egress no
nível de rede ou prontidão de HML/PRD.

## Estação local verificada em 2026-10-26

Verificação executada em 2026-10-26. Ela descreve apenas a estação de
desenvolvimento e não comprova disponibilidade institucional ou prontidão do
serviço:

| Componente | Evidência local |
|---|---|
| Docker | CLI 29.8.1 instalada na verificação inicial; posteriormente a sandbox versionada passou por preflight, conforme a evidência histórica de 2026-10-26. |
| PostgreSQL | Backend aponta para instância on-premises fora do Compose; cliente `psql` 16.15 instalado. A sandbox Docker em `127.0.0.1:55432` é usada apenas pelo settings especial de testes e está em reavaliação. |
| Redis | Binário 7.0.15 instalado; instância dedicada não comprovada. |
| Memcached | Binário 1.6.24 instalado; instância dedicada não comprovada. |
| Object storage | SeaweedFS/S3 existe somente na sandbox Docker; não prova storage institucional. |
| ClamAV | Existe somente como serviço da sandbox Docker; não prova scanner institucional. |
| OpenBao | Existe somente como secrets manager da sandbox Docker; não prova provedor institucional. |
| Nginx | Existe somente como proxy TLS da sandbox Docker; não prova gateway/CDN institucional. |

Nenhum desses itens ausentes deverá ser instalado por suposição. Para DEV será
aprovada uma implementação local de cada contrato. Ambientes futuros escolherão
seus serviços e instalarão apenas os clientes ou agentes correspondentes.

## Lacunas confirmadas

| ID | Lacuna | Bloqueio | Decisão/evidência necessária |
|---|---|---|---|
| INF-001 | S3 e identidades de privilégio mínimo foram testados na sandbox; cliente e política da aplicação ainda não foram aprovados. | P0 para DEV | Aprovar o serviço de DEV, retenção/versionamento e adapter; repetir o gate por ambiente. |
| INF-002 | ClamAV/EICAR e falha fechada foram testados na sandbox; quarentena e workflow genérico ainda não existem na aplicação. | P0 para DEV | Aprovar scanner, estados de quarentena, adapter e suíte comum; repetir o gate por ambiente. |
| INF-003 | Nginx/TLS e limites existem na sandbox; purge e gateway/CDN do ambiente alvo não estão definidos. | P0 para contrato de DEV; P1 antes de CDN | Aprovar proxy local e interface de purge; escolher produto somente no gate do ambiente que usar CDN. |
| INF-004 | OpenBao/AppRole foi comprovado na sandbox e em CargaRH; cobertura geral e provedor institucional permanecem abertos. | P0 para DEV; novo gate por ambiente | Aprovar uso em DEV, inventariar segredos restantes e comprovar recuperação/negações. |
| INF-005 | Existe contrato aplicativo contra SSRF, mas não há comprovação de egress no nível de rede. | P0 para DEV; novo gate por ambiente | Permitir destino aprovado e bloquear loopback, redes privadas, link-local e metadata no controle de rede. |
| INF-006 | Restore foi provado somente na sandbox Docker, não na instância on-premises real. | P0 para DEV; novo gate por ambiente | Procedimento e restore da instância real; frequência, retenção e criptografia próprias em HML/PRD. |
| INF-007 | RPO, RTO e SLA não foram aprovados. | P1 antes de cada ambiente não local | Categorias e responsáveis definidos em DEV; valores aprovados no ambiente alvo. |
| INF-008 | Logs locais/redação foram comprovados; métricas, traces, correlação ponta a ponta e alerta recebido não foram. | P0 para contrato DEV; P1 para centralização futura | Completar telemetria exportável e exercício de alerta; escolher plataforma/retenção por ambiente. |
| INF-009 | Host interno server-only do SSR não está definido. | P0 para contrato de DEV; novo gate por ambiente | Variável server-only, TLS local e timeout; DNS próprio no ambiente alvo. |
| INF-010 | Estratégia e adapter de purge ainda não estão definidos, apesar do proxy local. | P0 para contrato/teste local; P1 antes de CDN | Interface, retry e TTL conforme ADR-0005; provedor escolhido no ambiente alvo. |

## Decisões que não podem ser inferidas do código

- fornecedor de object storage;
- ferramenta de antivírus/sandbox;
- gateway/CDN e domínio público;
- secrets manager;
- rede/egress institucional;
- política jurídica de retenção;
- SLA, RPO e RTO;
- responsáveis e contatos de incidente.

`PUB-020` e `PUB-022` permanecem pendentes até que essas escolhas tenham dono,
aprovação e evidência operacional atual. A evidência da sandbox é útil, mas não
encerra o banco real, o egress de rede ou a observabilidade. A Fase 1 e qualquer
teste sintético ficam bloqueados até o gate de pré-implementação ser comprovado.
