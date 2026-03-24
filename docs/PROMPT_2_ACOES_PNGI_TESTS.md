# PROMPT 2 — Testes do domínio acoes_pngi

**Pré-requisito**: PROMPT 1 concluído. Leia `docs/ARCH_SNAPSHOT.md`.

---

## Objetivo

Criar a suite de testes de `apps/acoes_pngi/tests/`
com a mesma qualidade e padrão de `apps/accounts/tests/`.

---

## Padrão de Teste (obrigatório)

```python
# Autenticação: SEMPRE via login real — nunca force_authenticate
import pytest
from rest_framework.test import APIClient

@pytest.fixture
def auth_client(db, django_user_model, app_acoes_pngi, role_gestor):
    user = django_user_model.objects.create_user("gestor", password="senha123")
    # criar UserProfile, UserRole...
    client = APIClient()
    resp = client.post("/accounts/auth/login/", {
        "username": "gestor", "password": "senha123",
        "app_context": "ACOES_PNGI"
    })
    assert resp.status_code == 200
    return client  # client já tem cookie sessionid
```

### Markers obrigatórios:
```python
@pytest.mark.django_db(transaction=True)  # sempre transaction=True
```

### Não usar:
- `SimpleTestCase`
- `force_authenticate`
- `force_login`
- Mocks de autenticação

---

## Estrutura de arquivos

```
apps/acoes_pngi/tests/
  __init__.py          (já existe)
  conftest.py          (criar)
  test_models.py       (criar)
  test_acoes_api.py    (criar)
  test_vigencia_api.py (criar)
  test_permissions.py  (criar)
  policies/
    __init__.py
    test_gestor_pngi.py
    test_coordenador_pngi.py
    test_operador_acao.py
    test_consultor_pngi.py
```

---

## Fixtures necessárias — `conftest.py`

```python
# apps/acoes_pngi/tests/conftest.py
import pytest
from rest_framework.test import APIClient
from apps.accounts.models import Aplicacao, Role, UserRole, UserProfile
from apps.acoes_pngi.models import Eixo, SituacaoAcao, VigenciaPNGI, Acoes


@pytest.fixture
def app_acoes_pngi(db):
    return Aplicacao.objects.create(
        codigointerno="ACOES_PNGI",
        nomeaplicacao="Ações PNGI",
        isappproductionready=True,
    )


@pytest.fixture
def role_gestor(db, app_acoes_pngi):
    return Role.objects.create(
        aplicacao=app_acoes_pngi,
        codigoperfil="GESTOR_PNGI",
        nomeperfil="Gestor PNGI",
    )


@pytest.fixture
def role_coordenador(db, app_acoes_pngi):
    return Role.objects.create(
        aplicacao=app_acoes_pngi,
        codigoperfil="COORDENADOR_PNGI",
        nomeperfil="Coordenador PNGI",
    )


@pytest.fixture
def role_operador(db, app_acoes_pngi):
    return Role.objects.create(
        aplicacao=app_acoes_pngi,
        codigoperfil="OPERADOR_ACAO",
        nomeperfil="Operador de Ação",
    )


@pytest.fixture
def role_consultor(db, app_acoes_pngi):
    return Role.objects.create(
        aplicacao=app_acoes_pngi,
        codigoperfil="CONSULTOR_PNGI",
        nomeperfil="Consultor PNGI",
    )


def _make_user_with_role(db, django_user_model, app, role, orgao="ES"):
    """Helper interno: cria user + profile + userrole."""
    from apps.accounts.models import StatusUsuario, TipoUsuario, ClassificacaoUsuario
    username = f"user_{role.codigoperfil.lower()}"
    user = django_user_model.objects.create_user(username, password="gpp@2026")
    UserProfile.objects.create(
        user=user,
        name=username,
        orgao=orgao,
        status_usuario=StatusUsuario.objects.get(pk=1),
        tipo_usuario=TipoUsuario.objects.get(pk=1),
        classificacao_usuario=ClassificacaoUsuario.objects.get(pk=1),
    )
    UserRole.objects.create(user=user, aplicacao=app, role=role)
    return user


@pytest.fixture
def gestor_client(db, django_user_model, app_acoes_pngi, role_gestor):
    user = _make_user_with_role(db, django_user_model, app_acoes_pngi, role_gestor)
    client = APIClient()
    resp = client.post("/accounts/auth/login/", {
        "username": user.username, "password": "gpp@2026",
        "app_context": "ACOES_PNGI"
    })
    assert resp.status_code == 200
    return client


@pytest.fixture
def consultor_client(db, django_user_model, app_acoes_pngi, role_consultor):
    user = _make_user_with_role(db, django_user_model, app_acoes_pngi, role_consultor)
    client = APIClient()
    resp = client.post("/accounts/auth/login/", {
        "username": user.username, "password": "gpp@2026",
        "app_context": "ACOES_PNGI"
    })
    assert resp.status_code == 200
    return client


@pytest.fixture
def vigencia(db):
    from django.utils import timezone
    return VigenciaPNGI.objects.create(
        strdescricao="PNGI 2025-2028",
        datiniciovigencia="2025-01-01",
    )


@pytest.fixture
def acao(db, vigencia):
    return Acoes.objects.create(
        strapelido="ACAO-001",
        strdescricaoacao="Descrição da ação de teste",
        strdescricaoentrega="Entrega esperada",
        idvigenciapngi=vigencia,
        orgao="ES",
    )
```

---

## Testes por arquivo

### `test_models.py` — Validação das constraints de banco

```python
@pytest.mark.django_db(transaction=True)
def test_acoes_herda_auditablemodel(acao):
    """created_by_id/name devem existir como campos simples (não FK)."""
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'tblacoes'"
        )
        cols = [r[0] for r in cursor.fetchall()]
    assert "created_by_id" in cols
    assert "created_by_name" in cols
    assert "updated_by_id" in cols
    assert "updated_by_name" in cols


@pytest.mark.django_db(transaction=True)
def test_acoes_sem_fk_para_auth_user(db):
    """Tabela tblacoes não deve ter FK referenciando auth_user."""
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.table_constraints tc
            JOIN information_schema.referential_constraints rc
              ON tc.constraint_name = rc.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON rc.unique_constraint_name = ccu.constraint_name
            WHERE tc.table_name = 'tblacoes'
              AND ccu.table_name = 'auth_user'
        """)
        count = cursor.fetchone()[0]
    assert count == 0, "tblacoes não deve ter FK para auth_user"
```

### `test_acoes_api.py` — CRUD completo

```
test_list_acoes_sem_autenticacao → 401
test_list_acoes_gestor → 200, lista vazia ou com dados do orgao
test_list_acoes_nao_ve_outro_orgao → IDOR: cria acao orgao=RJ, gestor orgao=ES nao ve
test_create_acao_gestor → 201, orgao preenchido automaticamente
test_create_acao_consultor → 403 (consultor nao tem WRITE)
test_update_acao_gestor → 200
test_delete_acao_gestor → 204
test_delete_acao_operador → 403 (operador nao tem DELETE)
```

### `test_permissions.py` — Matriz de roles

```
# Para cada role x operação:
GESTOR_PNGI     → list ✅ create ✅ update ✅ delete ✅
COORDENADOR_PNGI → list ✅ create ✅ update ✅ delete ❌
OPERADOR_ACAO   → list ✅ create ✅ update ✅ delete ❌
CONSULTOR_PNGI  → list ✅ create ❌ update ❌ delete ❌
SEM_ROLE        → todas ❌
```

### `policies/test_gestor_pngi.py`

```python
class TestGestorPNGI:
    """GESTOR_PNGI tem acesso total: READ + WRITE + DELETE."""

    @pytest.mark.django_db(transaction=True)
    def test_pode_listar(self, gestor_client): ...

    @pytest.mark.django_db(transaction=True)
    def test_pode_criar(self, gestor_client, vigencia): ...

    @pytest.mark.django_db(transaction=True)
    def test_pode_deletar(self, gestor_client, acao): ...
```

---

## Critérios de Conclusão

- [ ] `pytest apps/acoes_pngi/ -v` — ZERO FAILED
- [ ] Cobertura das 4 roles × 4 operações (16 cenários mínimos)
- [ ] Teste de IDOR: orgao ES não vê dados de orgao RJ
- [ ] Teste confirma ausência de FK auth_user no banco
- [ ] `pytest apps/ -v` — suite completa continua verde
