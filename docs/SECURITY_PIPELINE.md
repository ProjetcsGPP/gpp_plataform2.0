# GPP Plataform 2.0 — Pipeline de Segurança e Qualidade

**Última revisão**: 2026-04-01  
**Branch de referência**: `main`  
**Workflow**: [`.github/workflows/security.yml`](../.github/workflows/security.yml)

> Este documento descreve o pipeline automatizado de segurança e qualidade configurado
> via GitHub Actions. Para arquitetura geral do projeto, ver [`ARCH_SNAPSHOT.md`](./ARCH_SNAPSHOT.md).

---

## Visão Geral do Pipeline

O workflow `security.yml` é disparado em **dois eventos**:

| Evento | Quando |
|---|---|
| `push` | Em qualquer push para a branch `main` |
| `pull_request` | Em qualquer PR aberto contra qualquer branch |

> **Proteção contra forks**: o job `security` só executa quando o PR vem do mesmo
> repositório (`github.event.pull_request.head.repo.full_name == github.repository`)
> **ou** quando o evento é um `push` direto. Isso evita falha de permissão ao rodar
> scans que precisam de `security-events: write` em PRs de forks externos.

---

## Permissões do Workflow

```yaml
permissions:
  contents: read
  security-events: write
```

- `contents: read` — leitura do código fonte (princípio de menor privilégio).
- `security-events: write` — necessário para o CodeQL publicar alertas na aba
  **Security → Code scanning alerts** do repositório.

---

## Job 1: Security Scan (matriz paralela)

O job `security` executa **três ferramentas em paralelo** via `strategy.matrix`:

| Ferramenta | Foco | Falha o Build? |
|---|---|---|
| **CodeQL** | Análise estática de código Python (vulnerabilidades semânticas) | Não (`continue-on-error: true`) |
| **Gitleaks** | Detecção de segredos e credenciais no histórico Git | Sim |
| **Trivy** | Vulnerabilidades em dependências (`requirements.txt`) | Sim (CRITICAL/HIGH não corrigíveis) |

### CodeQL

Ferramenta da GitHub para análise de segurança semântica. Detecta classes de vulnerabilidade
como injeção de SQL, XSS, path traversal, uso inseguro de criptografia, entre outros.

- **Linguagem analisada**: `python`
- **Comportamento**: `continue-on-error: true` — o pipeline não é bloqueado em caso de
  falha técnica do CodeQL (ex.: timeout, erro de autobuild), mas alertas identificados
  ficam visíveis na aba **Security** do repositório.
- **Resultados**: acessíveis em [Security → Code scanning](https://github.com/ProjetcsGPP/gpp_plataform2.0/security/code-scanning).

> **Ação necessária**: alertas CodeQL devem ser triados na aba Security. Vulnerabilidades
> classificadas como `High` ou `Critical` pelo CodeQL devem ser resolvidas antes do merge.

### Gitleaks

Escâner de segredos que inspeciona todo o histórico de commits em busca de:

- Chaves de API, tokens OAuth, secrets JWT
- Credenciais de banco de dados, senhas hardcoded
- Chaves privadas SSH/TLS
- Qualquer string com padrão de credencial conhecida

> **Regra**: o Gitleaks **bloqueia o pipeline** se encontrar um segredo. Se um segredo
> for detectado por engano (falso positivo), crie um arquivo `.gitleaks.toml` na raiz
> com uma regra `[allowlist]` para o padrão específico.

### Trivy

Escâner de vulnerabilidades de dependências que analisa o sistema de arquivos completo
(`scan-type: fs`), incluindo `requirements.txt` e `requirements-dev.txt`.

- **Severidades verificadas**: `CRITICAL` e `HIGH` apenas
- **`ignore-unfixed: true`**: ignora CVEs sem correção disponível (reduz ruído de
  vulnerabilidades que o projeto não pode mitigar)
- **Resultado**: falha se houver CVE CRITICAL ou HIGH com correção disponível

> **Ação necessária**: quando o Trivy falhar, verifique qual pacote tem a vulnerabilidade
> e atualize para a versão corrigida no `requirements.txt`.

---

## Job 2: Tests (matriz paralela por suite)

O job `tests` executa **três suites de teste em paralelo** contra um banco PostgreSQL 14
provisado como service container:

| Suite | Comando | Objetivo |
|---|---|---|
| `auth` | `pytest apps/accounts/tests/test_multi_cookie.py` | Testa middleware de sessão multi-cookie |
| `policies` | `pytest apps/accounts/tests/policies/` | Testa matriz de roles RBAC/ABAC por role |
| `full` | `pytest --cov=apps --cov=common --cov-fail-under=80` | Suite completa com gate de cobertura ≥ 80% |

### Configuração do Ambiente de Teste

```yaml
env:
  DJANGO_SETTINGS_MODULE: config.settings.test
  SECRET_KEY: "test-secret-key"
  DB_NAME:     gpp_test
  DB_USER:     postgres
  DB_PASSWORD: postgres
  DB_HOST:     localhost
  DB_PORT:     5432
```

As variáveis acima só existem **no contexto do runner de CI**. Em ambiente local, o
`config/settings/test.py` deve ser configurado de forma equivalente (ver abaixo).

### `fail-fast: true`

Se qualquer suite falhar, as demais são canceladas imediatamente. Isso evita consumo
desnecessário de minutos de CI quando há uma falha crítica na suite `full`.

### Gate de Cobertura (suite `full`)

```bash
pytest --cov=apps --cov=common --cov-fail-under=80
```

A suite `full` **bloqueia o pipeline** se a cobertura cair abaixo de **80%**.
O relatório de cobertura é exibido no log da action com `--cov-report=term-missing`
(exibe linhas não cobertas).

> **Meta de cobertura**: 80% é o piso mínimo. O objetivo de longo prazo é ≥ 90%,
> especialmente em `apps/accounts/` (IAM crítico) e `common/permissions.py`.

---

## Dependências de CI (`requirements-dev.txt`)

Os seguintes pacotes devem estar presentes em `requirements-dev.txt` para o pipeline
funcionar corretamente:

```
pytest
pytest-django
pytest-cov
djangorestframework  # (já em requirements.txt)
```

O runner instala ambos os arquivos:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## Práticas de Segurança Implementadas no Código

Além do pipeline, o projeto implementa defesas em camadas diretamente no código:

### Autenticação

| Mecanismo | Implementação |
|---|---|
| Sessão Django (httpOnly cookie) | `SESSION_COOKIE_HTTPONLY = True` em `base.py` |
| Proteção CSRF | `SESSION_COOKIE_SAMESITE = "Lax"` + middleware Django CSRF |
| Sem tokens Bearer/JWT | Removidos na FASE-0; autenticação é 100% via sessão |

### Autorização

| Mecanismo | Implementação |
|---|---|
| RBAC (Role-Based) | `HasRolePermission` em `common/permissions.py` |
| ABAC (Attribute-Based) | `Attribute` model em `apps/accounts/` |
| Tenant scoping (IDOR) | `SecureQuerysetMixin` — fail-closed quando `scope_value` é `None` |
| Portal Admin bypass | Injetado pelo `AppContextMiddleware` apenas após validação do `codigoperfil` |

### Proteção de Dados

| Mecanismo | Implementação |
|---|---|
| Auditoria imutável | `AuditableModel` com snapshot de nome (sem FK para `auth_user`) |
| Segredos fora do código | `SECRET_KEY`, credenciais DB via variáveis de ambiente (nunca hardcoded) |
| Debug desativado em prod | `DEBUG = False` em `config/settings/production.py` |

---

## Como Rodar a Verificação de Segurança Localmente

### Trivy (dependências)

```bash
# Instalar Trivy: https://aquasecurity.github.io/trivy/
trivy fs . --severity CRITICAL,HIGH --ignore-unfixed
```

### Gitleaks (segredos)

```bash
# Instalar Gitleaks: https://github.com/gitleaks/gitleaks
gitleaks detect --source . --verbose
```

### Testes com cobertura

```bash
# Suite completa com gate de cobertura
pytest --cov=apps --cov=common --cov-report=term-missing --cov-fail-under=80

# Suite auth
pytest apps/accounts/tests/test_multi_cookie.py --cov=apps/accounts/middleware --cov-report=term-missing

# Suite policies
pytest apps/accounts/tests/policies/ --cov=apps/accounts/policies --cov-report=term-missing
```

---

## Interpretando Falhas do Pipeline

| Job | Etapa | Causa Comum | Ação |
|---|---|---|---|
| `security (gitleaks)` | Run Gitleaks | Credencial commitada | Remover do histórico com `git-filter-repo`; rotacionar a credencial imediatamente |
| `security (trivy)` | Run Trivy | CVE CRITICAL/HIGH com fix | Atualizar o pacote no `requirements.txt` |
| `security (codeql)` | Analyze | Falha técnica de build | Verificar log; o pipeline **não bloqueia** (`continue-on-error`) |
| `tests (auth)` | Run AUTH tests | Regressão no middleware de sessão | Rodar `pytest apps/accounts/tests/test_multi_cookie.py -v` localmente |
| `tests (policies)` | Run POLICY tests | Regressão na matriz de roles | Rodar `pytest apps/accounts/tests/policies/ -v` localmente |
| `tests (full)` | Run FULL suite | Cobertura < 80% ou teste quebrado | Verificar `--cov-report=term-missing` para identificar linhas descobertas |

---

## Links Rápidos

- [Workflow security.yml](https://github.com/ProjetcsGPP/gpp_plataform2.0/actions/workflows/security.yml)
- [Code scanning alerts](https://github.com/ProjetcsGPP/gpp_plataform2.0/security/code-scanning)
- [Histórico de execuções](https://github.com/ProjetcsGPP/gpp_plataform2.0/actions)
- [`ARCH_SNAPSHOT.md`](./ARCH_SNAPSHOT.md) — Arquitetura geral
- [`IAM_AUTENTICACAO.md`](./IAM_AUTENTICACAO.md) — Autenticação e autorização
- [`COMMON_INFRA.md`](./COMMON_INFRA.md) — Infraestrutura compartilhada
