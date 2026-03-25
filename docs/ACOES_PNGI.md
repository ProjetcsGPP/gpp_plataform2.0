# App `acoes_pngi` — Documentação do Domínio

**App label**: `acoes_pngi`
**Schema PostgreSQL**: `acoes_pngi`
**Última revisão**: 2026-03-25

> Para visão geral do projeto ver [`ARCH_SNAPSHOT.md`](./ARCH_SNAPSHOT.md).
> Para autenticação e roles ver [`IAM_AUTENTICACAO.md`](./IAM_AUTENTICACAO.md).

---

## Contexto de Domínio

`acoes_pngi` é o domínio central da plataforma GPP. Gerencia as **Ações do Programa PNGI**
(Programa Nacional de Gestão e Inovação) — iniciativas transversais que envolvem
múltiplos órgãos. Por isso:

- **Não usa `SecureQuerysetMixin`** — ações não são recursos de tenant
- Controle de acesso é **exclusivamente por roles** (`_load_role_matrix()`)
- O `orgao` do criador é registrado indiretamente via `created_by_id` (auditoria), sem campo denormalizado em `Acoes`

---

## Models

Todos os models de negócio herdam `AuditableModel`. Models de referência simples herdam apenas `models.Model`.

### `Eixo` (tbleixos) — `AuditableModel`

Eixo temático do programa PNGI (ex: Educação, Saúde, Infraestrutura).

| Campo | Tipo | |
|---|---|---|
| `ideixo` | `AutoField` PK | |
| `strdescricaoeixo` | `CharField(100)` | Descrição completa |
| `stralias` | `CharField(5)` unique | Sigla/alias |

`ordering`: `["stralias"]`

### `SituacaoAcao` (tblsituacaoacao) — `models.Model`

Tabela de referência: situações possíveis de uma Ação (ex: Em andamento, Concluída, Cancelada).

| Campo | Tipo | |
|---|---|---|
| `idsituacaoacao` | `AutoField` PK | |
| `strdescricaosituacao` | `CharField(50)` unique | |

`ordering`: `["strdescricaosituacao"]`

### `TipoEntraveAlerta` (tbltipoentravealerta) — `models.Model`

Tabela de referência: classifica o tipo de entrave ou alerta de uma Ação.

| Campo | Tipo | |
|---|---|---|
| `idtipoentravealerta` | `AutoField` PK | |
| `strdescricaotipoentravealerta` | `CharField(50)` | |

### `TipoAnotacaoAlinhamento` (tbltipoanotacaoalinhamento) — `models.Model`

Tabela de referência: tipo de anotação/comentário associado a uma Ação.

| Campo | Tipo | |
|---|---|---|
| `idtipoanotacaoalinhamento` | `AutoField` PK | |
| `strdescricaotipoanotacaoalinhamento` | `CharField(100)` | |

### `VigenciaPNGI` (tblvigenciapngi) — `AuditableModel`

Define o ciclo/período de vigência do programa PNGI. Todas as `Acoes` pertencem a uma vigência.

| Campo | Tipo | |
|---|---|---|
| `idvigenciapngi` | `AutoField` PK | |
| `strdescricao` | `CharField(200)` | Ex: `"PNGI 2025-2028"` |
| `datiniciovigencia` | `DateField` | Obrigatório |
| `datfinalvigencia` | `DateField` nullable | Vigência em aberto se null |

`ordering`: `["-datiniciovigencia"]`

### `Acoes` (tblacoes) — `AuditableModel` — **Entidade Principal**

Ação do programa PNGI. Entidade central do domínio.

| Campo | Tipo | |
|---|---|---|
| `idacao` | `AutoField` PK | |
| `strapelido` | `CharField(50)` | Código/apelido da ação |
| `strdescricaoacao` | `CharField(350)` | Descrição completa |
| `strdescricaoentrega` | `CharField(100)` | Descrição da entrega esperada |
| `datdataentrega` | `DateTimeField` nullable | Prazo de entrega |
| `idvigenciapngi` | FK `VigenciaPNGI` PROTECT | Obrigatório |
| `idtipoentravealerta` | FK `TipoEntraveAlerta` SET_NULL nullable | Opcional |
| `idsituacaoacao` | FK `SituacaoAcao` PROTECT nullable | Situação atual |
| `ideixo` | FK `Eixo` PROTECT nullable | Eixo temático |

`ordering`: `["strapelido"]`

> **Design deliberado**: `Acoes` não tem campo `orgao` nem FK para `auth_user`.
> O `orgao` do criador é recuperável indiretamente via `created_by_id` → `UserProfile.orgao`.
> Auditoria é preenchida automaticamente por `AuditableMixin`.

### `AcaoPrazo` (tblacaoprazo) — `AuditableModel`

Prazo associado a uma Ação. Uma ação pode ter múltiplos prazos.

| Campo | Tipo | |
|---|---|---|
| `idacaoprazo` | `AutoField` PK | |
| `idacao` | FK `Acoes` CASCADE | Recurso pai |
| `isacaoprazoativo` | `BooleanField` default=True | |
| `strprazo` | `CharField(50)` | Descrição do prazo |

### `AcaoDestaque` (tblacaodestaque) — `AuditableModel`

Marca uma Ação como destaque em uma data específica.

| Campo | Tipo | |
|---|---|---|
| `idacaodestaque` | `AutoField` PK | |
| `idacao` | FK `Acoes` CASCADE | Recurso pai |
| `datdatadestaque` | `DateTimeField` | Data do destaque |

### `AcaoAnotacaoAlinhamento` (tblacaoanotacaoalinhamento) — `AuditableModel`

Anotação/comentário tipificado associado a uma Ação.

| Campo | Tipo | |
|---|---|---|
| `idacaoanotacaoalinhamento` | `AutoField` PK | |
| `idacao` | FK `Acoes` CASCADE | Recurso pai |
| `idtipoanotacaoalinhamento` | FK `TipoAnotacaoAlinhamento` PROTECT | Tipo da anotação |
| `strdescricao` | `TextField` | Conteúdo |

### `RelacaoAcaoUsuarioResponsavel` (tblrelacaoacaousuarioresponsavel) — `models.Model`

Relação M:N entre uma Ação e usuários responsáveis.

| Campo | Tipo | |
|---|---|---|
| `idacao` | FK `Acoes` CASCADE | |
| `idusuarioresponsavel` | `IntegerField` | ID lógico (sem FK para `auth_user`) |

**Constraint**: `unique_together = (idacao, idusuarioresponsavel)`

> `idusuarioresponsavel` é chave lógica referenciando o `id` de `auth.User`.
> Não há FK explícita para evitar dependência cross-schema no teardown do pytest.

---

## Serializers (`apps/acoes_pngi/serializers.py`)

Todos os serializers de models que herdam `AuditableModel` devem herdar `AuditableModelSerializer`
(de `common/serializers.py`). Models de referência simples usam `ModelSerializer`.

| Serializer | Model | Base |
|---|---|---|
| `EixoSerializer` | `Eixo` | `AuditableModelSerializer` |
| `SituacaoAcaoSerializer` | `SituacaoAcao` | `ModelSerializer` |
| `TipoEntraveAlertaSerializer` | `TipoEntraveAlerta` | `ModelSerializer` |
| `VigenciaPNGISerializer` | `VigenciaPNGI` | `AuditableModelSerializer` |
| `AcoesSerializer` | `Acoes` | `AuditableModelSerializer` |
| `AcaoPrazoSerializer` | `AcaoPrazo` | `AuditableModelSerializer` |
| `AcaoDestaqueSerializer` | `AcaoDestaque` | `AuditableModelSerializer` |
| `AcaoAnotacaoAlinhamentoSerializer` | `AcaoAnotacaoAlinhamento` | `AuditableModelSerializer` |

Campos de auditoria (`created_by_id`, `created_by_name`, `updated_by_id`, `updated_by_name`,
`created_at`, `updated_at`) são herdados automaticamente de `AuditableModelSerializer` como `read_only`.

---

## ViewSets (`apps/acoes_pngi/views.py`)

### Mecanismo de Controle de Acesso

Cada ViewSet usa dois elementos:

1. **`HasRolePermission`** (em `permission_classes`) — valida se o usuário tem qualquer role ativa
2. **`_check_roles(request, level, matrix_fn)`** — chamado em cada método, valida o nível (READ/WRITE/DELETE)

`_load_role_matrix()` e `_load_vigencia_role_matrix()` usam `lru_cache(maxsize=1)` —
consultam o banco **uma única vez por worker**. Para recarregar: `_load_role_matrix.cache_clear()`.

`_check_roles` faz bypass automático se `request.is_portal_admin = True`.

### ViewSets Disponíveis

| ViewSet | Tipo | Herda | Matriz |
|---|---|---|---|
| `EixoViewSet` | `ReadOnlyModelViewSet` | `HasRolePermission` | `_load_role_matrix` |
| `SituacaoAcaoViewSet` | `ReadOnlyModelViewSet` | `HasRolePermission` | `_load_role_matrix` |
| `VigenciaPNGIViewSet` | `ModelViewSet` | `AuditableMixin` | `_load_vigencia_role_matrix` |
| `AcaoViewSet` | `ModelViewSet` | `AuditableMixin` | `_load_role_matrix` |
| `AcaoPrazoViewSet` | `ModelViewSet` | `AuditableMixin` | `_load_role_matrix` |
| `AcaoDestaqueViewSet` | `ModelViewSet` | `AuditableMixin` | `_load_role_matrix` |
| `AcaoAnotacaoViewSet` | `ModelViewSet` | `AuditableMixin` | `_load_role_matrix` |

### `AcaoViewSet` — Detalhes

```python
queryset = Acoes.objects.select_related(
    "idvigenciapngi",
    "idtipoentravealerta",
    "idsituacaoacao",
    "ideixo",
)
```

`AuditableMixin` preenche automaticamente `created_by_id/name` e `updated_by_id/name`
em `perform_create` e `perform_update`. **Não sobrescrever** esses métodos.

### ViewSets Nested (prazos, destaques, anotações)

Filtram pelo `acao_pk` capturado da URL via `self.kwargs["acao_pk"]`.
Usam a mesma matriz de roles de `Acoes`.

### Matriz de Permissões Detalhada

**Acoes, Eixo, SituacaoAcao, Prazos, Destaques, Anotações** (`_load_role_matrix`):

| Role | READ | WRITE | DELETE |
|---|---|---|---|
| `GESTOR_PNGI` | ✅ | ✅ | ✅ |
| `COORDENADOR_PNGI` | ✅ | ✅ | ❌ |
| `OPERADOR_ACAO` | ✅ | ✅ | ❌ |
| `CONSULTOR_PNGI` | ✅ | ❌ | ❌ |

**VigenciaPNGI** (`_load_vigencia_role_matrix`) — OPERADOR_ACAO só lê:

| Role | READ | WRITE | DELETE |
|---|---|---|---|
| `GESTOR_PNGI` | ✅ | ✅ | ✅ |
| `COORDENADOR_PNGI` | ✅ | ✅ | ❌ |
| `OPERADOR_ACAO` | ✅ | ❌ | ❌ |
| `CONSULTOR_PNGI` | ✅ | ❌ | ❌ |

---

## URLs (`apps/acoes_pngi/urls.py`)

`app_name = "acoes_pngi"` — montado em `/api/acoes-pngi/` pelo router global.

### Rotas Planas

| Método | Path | ViewSet | Nome |
|---|---|---|---|
| GET/POST | `/api/acoes-pngi/acoes/` | `AcaoViewSet` | `acoes_pngi:acao-list` |
| GET/PUT/PATCH/DELETE | `/api/acoes-pngi/acoes/{id}/` | `AcaoViewSet` | `acoes_pngi:acao-detail` |
| GET/POST | `/api/acoes-pngi/eixos/` | `EixoViewSet` | `acoes_pngi:eixo-list` |
| GET | `/api/acoes-pngi/eixos/{id}/` | `EixoViewSet` | `acoes_pngi:eixo-detail` |
| GET/POST | `/api/acoes-pngi/situacoes/` | `SituacaoAcaoViewSet` | `acoes_pngi:situacao-list` |
| GET | `/api/acoes-pngi/situacoes/{id}/` | `SituacaoAcaoViewSet` | `acoes_pngi:situacao-detail` |
| GET/POST | `/api/acoes-pngi/vigencias/` | `VigenciaPNGIViewSet` | `acoes_pngi:vigencia-list` |
| GET/PUT/PATCH/DELETE | `/api/acoes-pngi/vigencias/{id}/` | `VigenciaPNGIViewSet` | `acoes_pngi:vigencia-detail` |

### Rotas Nested (sob `/api/acoes-pngi/acoes/{acao_pk}/`)

| Método | Path | ViewSet | Nome |
|---|---|---|---|
| GET/POST | `acoes/{acao_pk}/prazos/` | `AcaoPrazoViewSet` | `acoes_pngi:acao-prazo-list` |
| GET/PUT/PATCH/DELETE | `acoes/{acao_pk}/prazos/{id}/` | `AcaoPrazoViewSet` | `acoes_pngi:acao-prazo-detail` |
| GET/POST | `acoes/{acao_pk}/destaques/` | `AcaoDestaqueViewSet` | `acoes_pngi:acao-destaque-list` |
| GET/PUT/PATCH/DELETE | `acoes/{acao_pk}/destaques/{id}/` | `AcaoDestaqueViewSet` | `acoes_pngi:acao-destaque-detail` |
| GET/POST | `acoes/{acao_pk}/anotacoes/` | `AcaoAnotacaoViewSet` | `acoes_pngi:acao-anotacao-list` |
| GET/PUT/PATCH/DELETE | `acoes/{acao_pk}/anotacoes/{id}/` | `AcaoAnotacaoViewSet` | `acoes_pngi:acao-anotacao-detail` |

Implementado com `rest_framework_nested.routers.NestedDefaultRouter`.

---

## Testes (`apps/acoes_pngi/tests/`)

### Estrutura

```
apps/acoes_pngi/tests/
  __init__.py
  conftest.py              # Fixtures: app, roles, users, vigencia, acao
  test_models.py           # Constraints de banco, herança AuditableModel
  test_acoes_api.py        # CRUD completo de Acoes
  test_vigencia_api.py     # CRUD de VigenciaPNGI
  test_permissions.py      # Matriz roles × operações
  policies/
    __init__.py
    test_gestor_pngi.py
    test_coordenador_pngi.py
    test_operador_acao.py
    test_consultor_pngi.py
```

### Regras Obrigatórias

```python
# SEMPRE transaction=True
@pytest.mark.django_db(transaction=True)

# NUNCA force_authenticate ou force_login
# SEMPRE autenticar via login real
client.post("/api/accounts/auth/login/", {
    "username": user.username,
    "password": "gpp@2026",
    "app_context": "ACOES_PNGI",
})
```

### Fixtures Principais (`conftest.py`)

| Fixture | Descrição |
|---|---|
| `app_acoes_pngi` | `Aplicacao(codigointerno="ACOES_PNGI")` |
| `role_gestor` | `Role(codigoperfil="GESTOR_PNGI")` |
| `role_coordenador` | `Role(codigoperfil="COORDENADOR_PNGI")` |
| `role_operador` | `Role(codigoperfil="OPERADOR_ACAO")` |
| `role_consultor` | `Role(codigoperfil="CONSULTOR_PNGI")` |
| `gestor_client` | `APIClient` autenticado como `GESTOR_PNGI` |
| `consultor_client` | `APIClient` autenticado como `CONSULTOR_PNGI` |
| `vigencia` | `VigenciaPNGI(strdescricao="PNGI 2025-2028", ...)` |
| `acao` | `Acoes` básica vinculada à `vigencia` |

### Cenários Mínimos

- 4 roles × 4 operações = 16 cenários de permissão
- `401` para requisições sem autenticação
- Confirmação de ausência de FK `auth_user` no banco (`tblacoes`)
- Validação dos campos de auditoria via `information_schema`

---

## Backlog Específico

| # | Item | Status |
|---|---|---|
| 1 | Testes nested resources (prazos, destaques, anotações) | 🟡 identificado |
| 2 | Testes de `RelacaoAcaoUsuarioResponsavel` | 🟡 identificado |
| 3 | Endpoint de associação de responsáveis via API | 🔴 não implementado |
| 4 | Filtros de listagem em `AcaoViewSet` (por vigência, situação, eixo) | 🔴 não implementado |
