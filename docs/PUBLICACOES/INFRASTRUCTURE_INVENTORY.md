# Inventário de Infraestrutura — Fase 0

**Data da verificação:** 2026-10-26  
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

## Estação local verificada

Verificação executada em 2026-10-26. Ela descreve apenas a estação de
desenvolvimento e não comprova disponibilidade institucional ou prontidão do
serviço:

| Componente | Evidência local |
|---|---|
| Docker | CLI 29.8.1 instalada; daemon/ambiente não comprovado. |
| PostgreSQL | Backend aponta para instância on-premises fora do Compose; cliente `psql` 16.15 instalado. A sandbox Docker em `127.0.0.1:55432` é usada apenas pelo settings especial de testes e está em reavaliação. |
| Redis | Binário 7.0.15 instalado; instância dedicada não comprovada. |
| Memcached | Binário 1.6.24 instalado; instância dedicada não comprovada. |
| MinIO/S3 CLI | Não instalado. Isso não prova ausência de storage institucional. |
| ClamAV | Não instalado. Isso não prova ausência de scanner institucional. |
| Vault | Não instalado. Isso não prova ausência de secrets manager institucional. |
| Nginx | Não instalado. Isso não prova ausência de gateway/reverse proxy institucional. |

Nenhum desses itens ausentes deverá ser instalado por suposição. Para DEV será
aprovada uma implementação local de cada contrato. Ambientes futuros escolherão
seus serviços e instalarão apenas os clientes ou agentes correspondentes.

## Lacunas confirmadas

| ID | Lacuna | Bloqueio | Decisão/evidência necessária |
|---|---|---|---|
| INF-001 | Object storage não configurado; `boto3`/`django-storages` não estão nas dependências. | P0 para DEV | Implementação S3 local, buckets privados, versionamento e teste de acesso; novo gate por ambiente. |
| INF-002 | Não existe antivírus, sandbox ou quarentena genérica de upload. | P0 para DEV | Scanner local, estados de quarentena e política de falha fechada; novo gate por ambiente. |
| INF-003 | Gateway/CDN de produção não está documentado. | P0 para proxy/contrato de DEV; P1 antes de CDN | Reverse proxy local, TLS, limites, headers e interface de purge; produto futuro não é pressuposto. |
| INF-004 | Secrets manager institucional não está definido. | P0 para implementação local; novo gate por ambiente | Serviço de DEV, autenticação, rotação e auditoria; provedor futuro não é pressuposto. |
| INF-005 | Política de egress não existe no repositório. | P0 para DEV; novo gate por ambiente | Rede interna, mock allowlisted, bloqueio de saída e testes SSRF; política futura própria. |
| INF-006 | Restore foi provado somente na sandbox Docker, não na instância on-premises real. | P0 para DEV; novo gate por ambiente | Procedimento e restore da instância real; frequência, retenção e criptografia próprias em HML/PRD. |
| INF-007 | RPO, RTO e SLA não foram aprovados. | P1 antes de cada ambiente não local | Categorias e responsáveis definidos em DEV; valores aprovados no ambiente alvo. |
| INF-008 | Logs são locais e não há métricas/alertas centralizados comprovados. | P0 para formato/redação; P1 para centralização futura | Logs estruturados e redigidos em DEV; plataforma e retenção no ambiente alvo. |
| INF-009 | Host interno server-only do SSR não está definido. | P0 para contrato de DEV; novo gate por ambiente | Variável server-only, TLS local e timeout; DNS próprio no ambiente alvo. |
| INF-010 | Estratégia de purge distribuído não está definida. | P0 para contrato/teste local; P1 antes de CDN | Interface, retry e TTL conforme ADR-0005; provedor escolhido no ambiente alvo. |

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
aprovação e evidência operacional. A Fase 1 e qualquer teste sintético ficam
bloqueados até o gate de pré-implementação ser comprovado.
