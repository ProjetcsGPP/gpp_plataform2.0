# GPP Plataform 2.0

> **Plataforma de Gestão de Processos do Governo** — API REST multi-app construída com Django 5.2 + Django REST Framework.  
> Autenticação via sessão multi-cookie, RBAC hierárquico e arquitetura multi-schema PostgreSQL.

---

## Índice

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Apps](#apps)
- [Stack Tecnológica](#stack-tecnológica)
- [Pré-requisitos](#pré-requisitos)
- [Instalação e Configuração](#instalação-e-configuração)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Banco de Dados](#banco-de-dados)
- [Autenticação — Multi-Cookie Auth](#autenticação--multi-cookie-auth)
- [RBAC — Controle de Acesso](#rbac--controle-de-acesso)
- [Endpoints Principais](#endpoints-principais)
- [Rodando os Testes](#rodando-os-testes)
- [Coverage](#coverage)
- [Estrutura de Diretórios](#estrutura-de-diretórios)
- [Configurações por Ambiente](#configurações-por-ambiente)
- [Segurança](#segurança)
- [Contribuindo](#contribuindo)

---

## Visão Geral

A GPP Plataform 2.0 é uma API centralizada que serve múltiplas aplicações governamentais sob um único backend Django. Cada aplicação possui seu próprio contexto de autenticação (cookie de sessão dedicado), schema PostgreSQL isolado e conjunto de roles/permissões.

**Branch principal de desenvolvimento:** `Main`
---
## Branchs para desenvolvimento ou de correção devem ser criadas para novas funcionalidades
## Veja em [Convenções de Branch](https://github.com/ProjetcsGPP/gpp_plataform2.0/blob/main/README.md#conven%C3%A7%C3%B5es-de-branch) para maiores detalhes.
---

## Arquitetura

```
┌─────────────────────────────────────────────────────┐
│                   Cliente (Frontend)                 │
│         Next.js / Browser / API Consumer             │
└────────────┬──────────────┬──────────────────────────┘
             │              │
     gpp_session_ACOES_PNGI │ gpp_session_PORTAL
             │              │
┌────────────▼──────────────▼──────────────────────────┐
│              Django Middleware Pipeline               │
│  AppContextMiddleware  →  AuthorizationMiddleware     │
└────────────────────────┬──────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
 /api/accounts/   /api/acoes-pngi/  /api/portal/
  (transversal)   (app dedicada)   (app dedicada)
        │                │                │
        ▼                ▼                ▼
   accounts DB      acoes_pngi       portal DB
    (public)         schema           schema
```

O `AppContextMiddleware` resolve qual cookie `gpp_session_*` está presente na request e injeta `request.user` e `request.app_context` antes de qualquer view ser chamada. O `AuthorizationMiddleware` do `apps.core` bloqueia rotas protegidas para usuários não autenticados.

---

## Apps

| App | Prefixo URL | Schema DB | Descrição |
|---|---|---|---|
| `accounts` | `/api/accounts/` | `public` | Autenticação, RBAC, perfis, sessões |
| `portal` | `/api/portal/` | `public` | Portal central de administração |
| `acoes_pngi` | `/api/acoes-pngi/` | `acoes_pngi` | Ações do PNGI (Plano Nacional) |
| `carga_org_lot` | `/api/carga-org-lot/` | `carga_org_lot` | Carga de dados organizacionais |
| `core` | *(middleware/base)* | — | Middlewares, base views, utilities |

---

## Stack Tecnológica

- **Python** 3.14+
- **Django** 5.2
- **Django REST Framework** 3.16
- **PostgreSQL** (multi-schema via `DATABASE_ROUTERS`)
- **Memcached** (pymemcache) — cache de sessão e throttle
- **pytest** + **pytest-django** + **pytest-cov** — suíte de testes
- **django-environ** — gestão de variáveis de ambiente
- **django-cors-headers** — CORS
- **django-csp** ≥ 4.0 — Content Security Policy
- **pre-commit** — hooks de qualidade de código

---

## Pré-requisitos

- Python 3.14+
- PostgreSQL 14+
- Memcached 1.6+
- Git

> **Windows (desenvolvimento local):** recomenda-se WSL2 + Ubuntu para compatibilidade total com as dependências.

---

## Instalação e Configuração

```bash
# 1. Clone o repositório
git clone https://github.com/ProjetcsGPP/gpp_plataform2.0.git
cd gpp_plataform2.0

# 2. Crie e ative o ambiente virtual
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Linux/macOS
source .venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt
pip install -r requirements-dev.txt   # apenas em desenvolvimento

# 4. Configure as variáveis de ambiente
cp .env.example .env
# Edite o arquivo .env com suas credenciais locais

# 5. Aplique as migrações
python manage.py migrate

# 6. Crie o superusuário
python manage.py createsuperuser

# 7. Inicie o servidor de desenvolvimento
python manage.py runserver
```

---

## Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto com as seguintes variáveis:

```env
# Segurança
SECRET_KEY=sua-secret-key-aqui
ALLOWED_HOSTS=localhost,127.0.0.1

# Banco de dados
DB_NAME=gpp_plataform
DB_USER=postgres
DB_PASSWORD=sua-senha
DB_HOST=localhost
DB_PORT=5432

# Cache
MEMCACHED_LOCATION=127.0.0.1:11211

# CORS
CORS_ALLOWED_ORIGINS=http://localhost:3000

# CSRF
CSRF_TRUSTED_ORIGINS=http://localhost:3000
```

> **Nunca commite o arquivo `.env`.** Ele já está no `.gitignore`.

---

## Banco de Dados

O projeto utiliza **multi-schema PostgreSQL** com um `DATABASE_ROUTER` customizado (`config.routers.SchemaRouter`).

### Schemas

```sql
-- Criação dos schemas necessários (executar uma vez)
CREATE SCHEMA IF NOT EXISTS acoes_pngi;
CREATE SCHEMA IF NOT EXISTS carga_org_lot;
```

### Search Path

O `search_path` padrão configurado em `DATABASES.OPTIONS` é:

```
public, acoes_pngi, carga_org_lot
```

### Migrações por App

```bash
# Migrar todas as apps
python manage.py migrate

# Migrar apenas uma app específica
python manage.py migrate accounts
python manage.py migrate acoes_pngi
```

---

## Autenticação — Multi-Cookie Auth

A autenticação é baseada em **cookies de sessão dedicados por app** (sem JWT). Cada login gera um cookie `gpp_session_<APP_CONTEXT>` independente.

### Cookies por App

| App Context | Cookie Name |
|---|---|
| `ACOES_PNGI` | `gpp_session_ACOES_PNGI` |
| `CARGA_ORG_LOT` | `gpp_session_CARGA_ORG_LOT` |
| `PORTAL` | `gpp_session_PORTAL` |

### Login

```http
POST /api/accounts/login/
Content-Type: application/json

{
  "username": "usuario",
  "password": "senha",
  "app_context": "ACOES_PNGI"
}
```

**Resposta (200):** seta o cookie `gpp_session_ACOES_PNGI` no browser.

### Logout Seletivo

```http
POST /api/accounts/logout/ACOES_PNGI/
```

Revoga apenas a sessão da app informada. O cookie das demais apps permanece válido.

### Fallback Portal Admin

Um usuário com role `PORTAL_ADMIN` logado em `PORTAL` pode acessar qualquer app dedicada sem precisar de um segundo login. O `AppContextMiddleware` detecta automaticamente o cookie `gpp_session_PORTAL` e autentica via fallback.

---

## RBAC — Controle de Acesso

O sistema de permissões é hierárquico e baseado em **Roles por Aplicação**.

### Hierarquia de Roles

```
superuser  (Django is_superuser — acesso total)
    └── PORTAL_ADMIN  (acesso total via portal, sem alterar roles admin)
            └── GESTOR_<APP>  (gerencia usuários da app)
                    └── COORDENADOR_<APP>  (coordena ações específicas)
                            └── OPERADOR_<APP>  (operações básicas)
```

### Fixtures de Teste Disponíveis

As seguintes fixtures estão disponíveis globalmente via `conftest.py`:

| Fixture | Role | App |
|---|---|---|
| `superuser` | Django superuser | — |
| `portal_admin` | `PORTAL_ADMIN` | PORTAL |
| `gestor_pngi` | `GESTOR_PNGI` | ACOES_PNGI |
| `coordenador_pngi` | `COORDENADOR_PNGI` | ACOES_PNGI |
| `operador_acao` | `OPERADOR_ACAO` | ACOES_PNGI |
| `gestor_carga` | `GESTOR_CARGA` | CARGA_ORG_LOT |
| `usuario_sem_role` | *(sem role)* | — |
| `client_anonimo` | APIClient sem auth | — |
| `client_gestor` | APIClient autenticado | ACOES_PNGI |
| `client_coordenador` | APIClient autenticado | ACOES_PNGI |

---

## Endpoints Principais

### Accounts (`/api/accounts/`)

| Método | Endpoint | Descrição | Auth |
|---|---|---|---|
| `POST` | `/api/accounts/login/` | Login por app_context | ❌ |
| `POST` | `/api/accounts/logout/<slug>/` | Logout seletivo por app | ❌ |
| `GET` | `/api/accounts/me/` | Perfil do usuário logado | ✅ |
| `GET` | `/api/accounts/users/` | Lista usuários (admin) | ✅ |
| `GET` | `/api/accounts/roles/` | Lista roles | ✅ |
| `POST` | `/api/accounts/userroles/` | Atribui role a usuário | ✅ |
| `GET` | `/api/accounts/sessions/` | Lista sessões ativas | ✅ |
| `GET` | `/api/accounts/auth/` | Apps públicas (seletor de login) | ❌ |

### Health Check

```http
GET /api/health/
```

---

## Rodando os Testes

O projeto usa `pytest` com `pytest-django`. O banco de testes é reaproveitado entre runs (`--reuse-db`) para maior velocidade.

```bash
# Rodar todos os testes
pytest

# Rodar com recriação forçada do banco
pytest --create-db

# Rodar apenas uma app
pytest apps/accounts/tests/ -v

# Rodar apenas os testes de middleware multi-cookie
pytest apps/accounts/tests/test_multi_cookie.py -v

# Rodar apenas os testes de policies
pytest apps/accounts/tests/policies/ -v
```

### Configuração do pytest (`pytest.ini`)

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings.test
addopts = --reuse-db -v --cov=apps --cov=common --cov-report=term-missing
```

> **Throttle desabilitado em testes:** a fixture `_disable_throttle_session` (session-scoped, autouse) zera os rate limits durante toda a suite de testes.

---

## Coverage

```bash
# Coverage no terminal (padrão ao rodar pytest)
pytest --cov=apps --cov=common --cov-report=term-missing

# Gerar relatório HTML para uma app específica
pytest apps/accounts/tests/ --cov=apps/accounts --cov-report=html:htmlcov/accounts

# Abrir relatório (Windows PowerShell)
Start-Process "C:\Projects\gpp_plataform2.0\htmlcov\accounts\index.html"
```

---

## Estrutura de Diretórios

```
gpp_plataform2.0/
├── apps/
│   ├── accounts/           # Auth, RBAC, sessões, perfis
│   │   ├── middleware.py   # AppContextMiddleware (multi-cookie)
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   ├── policies/       # Lógica de autorização por recurso
│   │   └── tests/
│   │       ├── policies/   # Testes de policies
│   │       └── test_multi_cookie.py
│   ├── acoes_pngi/         # App PNGI (schema: acoes_pngi)
│   ├── carga_org_lot/      # App Carga (schema: carga_org_lot)
│   ├── core/               # Middlewares base, utilities
│   │   └── middleware/
│   │       ├── authorization.py
│   │       ├── application_context.py
│   │       └── role_context.py
│   └── portal/             # Portal administrativo
├── common/                 # Paginação, exceptions, utilitários globais
├── config/
│   ├── settings/
│   │   ├── base.py         # Configurações compartilhadas
│   │   ├── development.py  # Dev (DEBUG=True, SQLite-friendly)
│   │   ├── production.py   # Prod (HTTPS, cookies seguros)
│   │   └── test.py         # Testes (LocMemCache, DB isolado)
│   ├── urls.py             # Router principal
│   └── routers.py          # DatabaseRouter multi-schema
├── docs/                   # Documentação técnica adicional
├── scripts/                # Scripts utilitários (setup, seed, etc.)
├── conftest.py             # Fixtures globais do pytest
├── pytest.ini
├── requirements.txt
├── requirements-dev.txt
└── manage.py
```

---

## Configurações por Ambiente

| Configuração | Development | Test | Production |
|---|---|---|---|
| `DEBUG` | `True` | `False` | `False` |
| `SESSION_COOKIE_SECURE` | `False` | `False` | `True` |
| `CSRF_COOKIE_SECURE` | `False` | `False` | `True` |
| `CACHE_BACKEND` | `LocMemCache` | `LocMemCache` | `PyMemcacheCache` |
| `ALLOWED_HOSTS` | `localhost` | `*` | via `.env` |
| `SETTINGS_MODULE` | `config.settings.development` | `config.settings.test` | `config.settings.production` |

Para rodar em desenvolvimento:

```bash
DJANGO_SETTINGS_MODULE=config.settings.development python manage.py runserver
```

---

## Segurança

O projeto implementa as seguintes camadas de segurança:

- **Multi-cookie isolation:** cada app tem seu próprio cookie de sessão, evitando que um token comprometido afete outras apps
- **RBAC hierárquico:** permissões granulares por recurso, verificadas via `policies/`
- **CSP (Content Security Policy):** configurado via `django-csp` ≥ 4.0
- **CORS restrito:** apenas origens explicitamente listadas em `CORS_ALLOWED_ORIGINS`
- **CSRF:** habilitado para todas as mutações via DRF `SessionAuthentication`
- **Rate limiting:** throttle por usuário (`200/min`) e anônimo (`20/min`), com rate específico para login (`5/min`)
- **Security headers:** `X-Frame-Options: DENY`, `X-Content-Type-Options`, `XSS-Protection`
- **Cookies `HttpOnly` e `SameSite=Lax`** em todos os ambientes; `Secure=True` em produção
- **Logs de segurança:** handler dedicado `gpp.security` com rotação em `logs/security.log`

---

## Contribuindo

1. Crie uma branch a partir de `develop`: `git checkout -b feature/minha-feature`
2. Escreva testes para toda nova funcionalidade
3. Garanta que **todos os testes passam** antes do PR: `pytest`
4. Verifique que o coverage não diminuiu: `pytest --cov=apps --cov-report=term-missing`
5. Abra um Pull Request descrevendo as mudanças

### Convenções de Branch

| Prefixo | Uso |
|---|---|
| `feature/` | Nova funcionalidade |
| `fix/` | Correção de bug |
| `refactor/` | Refatoração sem mudança de comportamento |
| `docs/` | Documentação |
| `test/` | Adição/correção de testes |

---

> Projeto sob uso interno governamental — GPP Plataform 2.0 © 2026
