# GPP Plataform 2.0 — Snapshot de Arquitetura

**Data**: 2026-03-24
**Branch**: feature/acoes-pngi-policies
**Suite**: 346 passed, 1 skipped ✅

> Este documento é a fonte de verdade da arquitetura atual.
> Substitui `PROMPT_0_MODEL_AUDIT.md` (que refletia uma versão desatualizada).

---

## 1. Autenticação e Sessão

### Mecanismo: Cookie/Sessão Django (sem JWT)

A arquitetura **não usa JWT**. A autenticação é inteiramente baseada em sessão
Django com cookie `sessionid`. O fluxo é:

```
POST /accounts/auth/login/
  → Django autentica user
  → cria request.session (session_key gerado pelo Django)
  → cria AccountsSession (session_key, app_context, ip, user_agent)
  → retorna cookie sessionid httpOnly
```

### `AccountsSession` (accounts/models.py)

```python
class AccountsSession(models.Model):
    user         = ForeignKey(auth.User)
    session_key  = CharField(40)           # request.session.session_key
    app_context  = CharField(50, nullable) # ex: "PORTAL", "ACOES_PNGI"
    created_at   = DateTimeField(auto_now_add)
    expires_at   = DateTimeField
    revoked      = BooleanField(default=False)
    revoked_at   = DateTimeField(nullable)
    ip_address   = GenericIPAddressField(nullable)
    user_agent   = TextField
```

**Nota importante**: `jti` foi **removido**. O campo de controle é `session_key`.
A revogação é por `session_key`, não por token.

### `AppContextMiddleware` (accounts/middleware.py)

Ordem obrigatória em `MIDDLEWARE`:
```python
"django.contrib.sessions.middleware.SessionMiddleware",
"django.contrib.auth.middleware.AuthenticationMiddleware",
"apps.accounts.middleware.AppContextMiddleware",  # ← depois dos dois acima
```

O middleware:
- Popula `request.app_context` a partir de `request.session.get("app_context")`
- Popula `request.session_key`
- Bloqueia sessões com `AccountsSession.revoked=True` → logout + 401 JSON

---

## 2. IAM Central (accounts)

### Modelos

```
Aplicacao (tblaplicacao)
  idaplicacao (PK)
  codigointerno: CharField(50, unique)  ← ex: "PORTAL", "ACOES_PNGI"
  nomeaplicacao: CharField(200)
  base_url: URLField (nullable)
  isshowinportal: BooleanField
  isappbloqueada: BooleanField
  isappproductionready: BooleanField

UserProfile (tblusuario)
  user (PK, OneToOne): auth.User
  name: CharField(200)
  orgao: CharField(100, nullable)  ← órgão de lotacão do usuário
                                      Escopo de tenant apenas em apps que
                                      usam SecureQuerysetMixin (ex: carga_org_lot).
                                      Em acoes_pngi: apenas informativo/auditoria.
  status_usuario (FK): StatusUsuario
  tipo_usuario (FK): TipoUsuario
  classificacao_usuario (FK): ClassificacaoUsuario
  idusuariocriacao (FK, nullable): auth.User
  idusuarioalteracao (FK, nullable): auth.User
  datacriacao / data_alteracao: DateTimeField

Role (accounts_role)
  aplicacao (FK, nullable): Aplicacao
  nomeperfil: CharField(100)
  codigoperfil: CharField(100)  ← IDENTIFICADOR LÓGICO
  group (FK, nullable): auth.Group
  UNIQUE: (aplicacao, codigoperfil)

UserRole (accounts_userrole)
  user (FK): auth.User
  aplicacao (FK, nullable): Aplicacao
  role (FK): Role
  UNIQUE: (user, aplicacao)  ← 1 role por usuário por app

Attribute (accounts_attribute)  ← ABAC
  user (FK): auth.User
  aplicacao (FK, nullable): Aplicacao
  key: CharField(100)
  value: CharField(255)
  UNIQUE: (user, aplicacao, key)

ClassificacaoUsuario (tblclassificacaousuario)
  idclassificacaousuario (PK): SmallIntegerField
  strdescricao: CharField(100)
  pode_criar_usuario: BooleanField
  pode_editar_usuario: BooleanField
```

### Roles conhecidas em acoes_pngi

```
GESTOR_PNGI        → READ + WRITE + DELETE
COORDENADOR_PNGI   → READ + WRITE
OPERADOR_ACAO      → READ + WRITE
CONSULTOR_PNGI     → READ apenas
```

---

## 3. AuditableModel (common/models.py)

### Campos — SEM ForeignKey para auth_user

```python
class AuditableModel(models.Model):
    created_by_id   = IntegerField(null=True, editable=False)
    created_by_name = CharField(200, blank=True, editable=False)  # snapshot
    updated_by_id   = IntegerField(null=True, editable=False)
    updated_by_name = CharField(200, blank=True, editable=False)  # snapshot
    created_at      = DateTimeField(auto_now_add=True, editable=False)
    updated_at      = DateTimeField(auto_now=True, editable=False)
    class Meta:
        abstract = True
```

**Motivação**: elimina toda FK cross-schema/cross-db entre apps de negócio
e `auth_user`. Isso:
- Permite teardown limpo no pytest-django (sem TRUNCATE bloqueado por FK)
- Prepara cada app para banco de dados próprio no futuro
- Mantém histórico imutável mesmo após deleção de usuário

### Preenchimento automático — `AuditableMixin` (common/mixins.py)

```python
class AuditableMixin:
    def perform_create(self, serializer):
        user = self.request.user
        name = user.get_full_name().strip() or user.username
        serializer.save(
            created_by_id=user.pk,
            created_by_name=name,
            updated_by_id=user.pk,
            updated_by_name=name,
        )

    def perform_update(self, serializer):
        user = self.request.user
        name = user.get_full_name().strip() or user.username
        serializer.save(
            updated_by_id=user.pk,
            updated_by_name=name,
        )
```

### Serializer base — `AuditableModelSerializer` (common/serializers.py)

```python
class AuditableModelSerializer(serializers.ModelSerializer):
    created_by_id   = IntegerField(read_only=True)
    created_by_name = CharField(read_only=True)
    updated_by_id   = IntegerField(read_only=True)
    updated_by_name = CharField(read_only=True)
    created_at      = DateTimeField(read_only=True)
    updated_at      = DateTimeField(read_only=True)

    class Meta:
        fields = ["created_by_id", "created_by_name", "updated_by_id",
                  "updated_by_name", "created_at", "updated_at"]
        read_only_fields = fields
```

---

## 4. Segurança — `SecureQuerysetMixin` (common/mixins.py)

```python
class SecureQuerysetMixin:
    scope_field  = "orgao"  # campo no model
    scope_source = "orgao"  # atributo em request.user.profile

    def get_queryset(self):
        qs = super().get_queryset()
        return self.filter_queryset_by_scope(qs)

    def filter_queryset_by_scope(self, qs):
        # fail-closed: se scope_value for None → qs.none()
        ...
```

### Quando usar `SecureQuerysetMixin`

O mixin é um filtro de **escopo de tenant** — ele restringe o queryset
ao `orgao` do usuário autenticado. Deve ser usado **somente** em ViewSets
cujos recursos pertencem a um órgão específico:

| App / Resource | Usa `SecureQuerysetMixin`? | Motivo |
|---|---|---|
| `carga_org_lot` / `TokenEnvioCarga` | ✅ Sim | Carga pertence ao órgão do usuário |
| `acoes_pngi` / `Acoes` | ❌ **Não** | Ações são independentes de órgão — iniciativas do programa PNGI que podem envolver múltiplos órgãos |
| `acoes_pngi` / Tabelas de referência (`Eixo`, `SituacaoAcao`, etc.) | ❌ **Não** | São dados públicos da plataforma |

**Controle de acesso em `acoes_pngi` é feito exclusivamente por roles**
(`_load_role_matrix()` + `HasRolePermission`), não por escopo de órgão.

### Sobre `UserProfile.orgao` em `acoes_pngi`

`UserProfile.orgao` indica o órgão de lotação do usuário. Em `acoes_pngi`,
esse campo é **informativo** — pode aparecer em relatórios ou filtros
opcionais, mas **não controla visibilidade de registros**. A classe
`UsuarioResponsavel` (removida) tinha `strorgao` por razões históricas;
corrretamente removida pois duplicava o dado já presente em `UserProfile`.

---

## 5. apps/acoes_pngi — Estado Atual

### Models existentes

```
Eixo (tbleixos) — herda AuditableModel
  ideixo (PK), strdescricaoeixo, stralias (unique)

SituacaoAcao (tblsituacaoacao)
  idsituacaoacao (PK), strdescricaosituacao (unique)
  ⚠️ ainda sem FK em Acoes — desconectada

TipoEntraveAlerta (tbltipoentravealerta)
  idtipoentravealerta (PK), strdescricaotipoentravealerta

TipoAnotacaoAlinhamento (tbltipoanotacaoalinhamento)
  idtipoanotacaoalinhamento (PK), strdescricaotipoanotacaoalinhamento

VigenciaPNGI (tblvigenciapngi) — herda AuditableModel
  idvigenciapngi (PK), strdescricao, datiniciovigencia, datfinalvigencia (nullable)

Acoes (tblacoes) — herda AuditableModel
  idacao (PK)
  strapelido: CharField(50)
  strdescricaoacao: CharField(350)
  strdescricaoentrega: CharField(100)
  datdataentrega: DateTimeField (nullable)
  idvigenciapngi (FK, obrigatório): VigenciaPNGI
  idtipoentravealerta (FK, nullable): TipoEntraveAlerta
  ⚠️ Falta: idsituacaoacao (FK) — conectar a SituacaoAcao
  ⚠️ Falta: ideixo (FK) — conectar a Eixo
  ✅ orgao NAO é atributo de Acoes — ações são independentes de órgão;
     o orgao do criador fica registrado em created_by_id (chave para UserProfile)

AcaoPrazo (tblacaoprazo) — herda AuditableModel
  idacaoprazo (PK), idacao (FK), isacaoprazoativo, strprazo

AcaoDestaque (tblacaodestaque) — herda AuditableModel
  idacaodestaque (PK), idacao (FK), datdatadestaque

AcaoAnotacaoAlinhamento (tblacaoanotacaoalinhamento) — herda AuditableModel
  idacaoanotacaoalinhamento (PK), idacao (FK),
  idtipoanotacaoalinhamento (FK), strdescricao (TextField)

RelacaoAcaoUsuarioResponsavel (tblrelacaoacaousuarioresponsavel)
  idacao (FK): Acoes
  idusuarioresponsavel: IntegerField  ← chave lógica = auth.User.pk
                                         sem FK cross-schema para auth_user
  UNIQUE: (idacao, idusuarioresponsavel)
  ✅ Correto: sem FK cross-schema
  Nota: o orgao do responsável é consultado via UserProfile quando necessário
        para relatórios — não é denormalizado em Acoes
```

### Views — scaffold ativo

`AcaoPNGIViewSet` em `views.py` já existe com:
- `AuditableMixin` + `IsAuthenticated` + `HasRolePermission`
- `_load_role_matrix()` com `lru_cache(maxsize=1)` — carrega roles do banco uma vez
- Todas as actions retornam 501 — **domínio ainda não implementado**
- `_EmptyQueryset` placeholder ativo
- ❌ `SecureQuerysetMixin` presente no scaffold mas **deve ser removido**
  pois Acoes não é recurso de tenant

### Serializers — scaffold ativo

`serializers.py` vazio (apenas comentário de exemplo). Ainda não implementado.

### Testes — diretório vazio

`apps/acoes_pngi/tests/__init__.py` existe mas sem nenhum test file.

---

## 6. apps/carga_org_lot — Estado Atual

Ver análise original em `PROMPT_0_MODEL_AUDIT.md`.
A principal pendência é adicionar campo `orgao` a `TokenEnvioCarga`.
`carga_org_lot` **é** um recurso de tenant — `SecureQuerysetMixin` se
aplicará corretamente quando o campo `orgao` for adicionado.

---

## 7. common — Estado Atual

```
common/
  models.py      → AuditableModel (IntegerField snapshot, sem FK auth_user)
  mixins.py      → SecureQuerysetMixin + AuditableMixin
  serializers.py → AuditableModelSerializer (novo)
  permissions.py → HasRolePermission
  exceptions.py  → handlers padrão
  pagination.py  → paginação padrão
  urls.py        → urls base
```

---

## 8. Padrão de Teste (accounts como referência)

A suite de `accounts/tests/` é o padrão de qualidade a seguir:

```
conftest.py         → fixtures compartilhadas (user, app, role, session, client)
test_auth_session.py        → login/logout/revogação de sessão
test_auth_aplicacoes.py     → autenticação por app_context
test_authorization_service.py → AuthorizationService
test_aplicacoes.py          → CRUD de Aplicacao
test_users.py               → CRUD de UserProfile
test_userroles.py           → atribuição de roles
test_roles.py               → criação e constraints de Role
test_constraints.py         → violações de constraints
tests/policies/             → testes de policy por role
```

Padrão usado:
- `pytest-django` + `@pytest.mark.django_db(transaction=True)`
- `APIClient` do DRF
- Autenticação via `client.post("/accounts/auth/login/")` → cookie sessionid
- Sem `force_authenticate` — sempre testa o fluxo real de sessão
- Sem `SimpleTestCase` — sempre `django_db`

---

## 9. Próximos Passos (backlog priorizado)

| # | Escopo | Arquivo(s) | Status |
|---|--------|-----------|--------|
| 1 | Completar domain `acoes_pngi` | models.py + migrations | 🔴 pendente |
| 2 | Serializers `acoes_pngi` | serializers.py | 🔴 pendente |
| 3 | ViewSet `acoes_pngi` final | views.py | 🔴 pendente |
| 4 | Testes `acoes_pngi` | tests/ | 🔴 pendente |
| 5 | Campo `orgao` em `carga_org_lot` | models.py + migrations | 🟡 identificado |
| 6 | Campo `telefone` em `UserProfile` | accounts/models.py | 🟡 identificado |
