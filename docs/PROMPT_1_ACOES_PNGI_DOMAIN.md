# PROMPT 1 — Domínio acoes_pngi: Models, Serializers e ViewSets

**Pré-requisito**: leia `docs/ARCH_SNAPSHOT.md` antes de executar.

---

## Objetivo

Implementar o domínio completo de `acoes_pngi`:
1. Corrigir os 2 gaps no `models.py` (`idsituacaoacao` e `ideixo` em `Acoes`)
2. Implementar `serializers.py` usando `AuditableModelSerializer`
3. Substituir o scaffold placeholder em `views.py` pela implementação real
4. Gerar migration

---

## Contexto de Arquitetura

### Autenticação
Sessão Django + cookie `sessionid`. **Sem JWT, sem token no header**.
O usuário autenticado está disponível em `request.user` graças ao
`AppContextMiddleware` já configurado.

### AuditableModel
Os campos de auditoria são `created_by_id`, `created_by_name`,
`updated_by_id`, `updated_by_name`. **Sem `created_by` como FK**.
Preenchidos automaticamente pelo `AuditableMixin` — nunca manualmente.

### Acoes NÃO é recurso de tenant
`Acoes` é uma iniciativa do programa PNGI — pode envolver múltiplos
órgãos. **`AcaoViewSet` não deve herdar `SecureQuerysetMixin`**.
O controle de acesso é feito exclusivamente por **roles**
(`_load_role_matrix()` + `HasRolePermission`).

O `orgao` do usuário criador fica registrado indiretamente via
`created_by_id` (chave lógica para `UserProfile`) — disponibilizado
em relatórios sob demanda, sem campo denormalizado em `Acoes`.

### AuditableModelSerializer
Disponível em `common/serializers.py`. Todos os serializers de
`acoes_pngi` que herdam `AuditableModel` devem herdar dele:
```python
from common.serializers import AuditableModelSerializer

class AcoesSerializer(AuditableModelSerializer):
    class Meta(AuditableModelSerializer.Meta):
        model = Acoes
        fields = AuditableModelSerializer.Meta.fields + [
            "idacao",
            "strapelido",
            # ...
        ]
```

---

## Passo 1 — Corrigir `apps/acoes_pngi/models.py`

### 1.1 Conectar `Acoes` a `SituacaoAcao`

```python
# Em Acoes (adicionar ao bloco de FKs):
idsituacaoacao = models.ForeignKey(
    SituacaoAcao,
    db_column="idsituacaoacao",
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name="acoes",
    help_text="Situação atual da ação (ex: Em andamento, Concluída)."
)
```

### 1.2 Conectar `Acoes` a `Eixo`

```python
# Em Acoes (adicionar ao bloco de FKs):
ideixo = models.ForeignKey(
    Eixo,
    db_column="ideixo",
    on_delete=models.PROTECT,
    null=True,
    blank=True,
    related_name="acoes",
    help_text="Eixo temático ao qual a ação pertence."
)
```

---

## Passo 2 — Implementar `apps/acoes_pngi/serializers.py`

Um serializer por model que herda `AuditableModel`.
Models de referência simples (sem `AuditableModel`) usam `ModelSerializer`.

### Serializers necessários:

```
EixoSerializer              → Eixo                      (herda ModelSerializer)
SituacaoAcaoSerializer      → SituacaoAcao              (herda ModelSerializer)
VigenciaPNGISerializer      → VigenciaPNGI              (herda AuditableModelSerializer)
TipoEntraveAlertaSerializer → TipoEntraveAlerta         (herda ModelSerializer)
AcoesSerializer             → Acoes                     (herda AuditableModelSerializer)
AcaoPrazoSerializer         → AcaoPrazo                 (herda AuditableModelSerializer)
AcaoDestaqueSerializer      → AcaoDestaque              (herda AuditableModelSerializer)
AcaoAnotacaoAlinhamentoSerializer → AcaoAnotacaoAlinhamento (herda AuditableModelSerializer)
```

### Regras de serialização para `AcoesSerializer`:
- `idacao`, `strapelido`, `strdescricaoacao`, `strdescricaoentrega`,
  `datdataentrega` — leitura e escrita
- `idvigenciapngi`, `idtipoentravealerta`, `idsituacaoacao`, `ideixo` — write como PK int
- Campos de auditoria — herdados de `AuditableModelSerializer` (read-only)

---

## Passo 3 — Implementar `apps/acoes_pngi/views.py`

Substituir o scaffold placeholder pela implementação real.

### ViewSets necessários:

```
EixoViewSet             → Eixo (list + retrieve apenas)
SituacaoAcaoViewSet     → SituacaoAcao (list + retrieve)
VigenciaPNGIViewSet     → VigenciaPNGI (CRUD completo — GESTOR_PNGI)
AcaoViewSet             → Acoes (CRUD completo — com matrix de roles)
AcaoPrazoViewSet        → AcaoPrazo (nested em Acao)
AcaoDestaqueViewSet     → AcaoDestaque (nested em Acao)
AcaoAnotacaoViewSet     → AcaoAnotacaoAlinhamento (nested em Acao)
```

### Regras para `AcaoViewSet`:

```python
class AcaoViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Acoes sao independentes de orgao (iniciativas do programa PNGI).
    Controle de acesso exclusivamente por roles via _load_role_matrix().
    NAO herda SecureQuerysetMixin.
    """
    queryset = Acoes.objects.select_related(
        "idvigenciapngi", "idtipoentravealerta", "idsituacaoacao", "ideixo"
    )
    serializer_class = AcoesSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]

    def list(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_READ)
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_WRITE)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _check_roles(request, _LEVEL_DELETE)
        return super().destroy(request, *args, **kwargs)
```

### `AuditableMixin` já cobre `perform_create` e `perform_update`:

```python
# NAO precisa sobrescrever perform_create para injetar orgao.
# AuditableMixin preenche created_by_id, created_by_name,
# updated_by_id, updated_by_name automaticamente.
```

### Manter `_load_role_matrix()` do scaffold:

A função `_load_role_matrix()` com `lru_cache(maxsize=1)` que já existe
no scaffold está correta e deve ser mantida sem alterações.

---

## Passo 4 — Migration

Após editar `models.py`, gerar a migration:

```bash
python manage.py makemigrations acoes_pngi \
    --name add_situacao_eixo_to_acoes
```

Após gerar, verificar se a migration:
- Adiciona `idsituacaoacao_id` como FK nullable para `tblsituacaoacao`
- Adiciona `ideixo_id` como FK nullable para `tbleixos`
- **Não cria FK para `auth_user`** em nenhum campo
- **Não adiciona campo `orgao`** a `tblacoes`

---

## Critérios de Conclusão

- [ ] `makemigrations` sem warnings
- [ ] `migrate` aplica sem erro
- [ ] `AcaoViewSet` funcional com queryset real (sem `SecureQuerysetMixin`)
- [ ] Todos os serializers herdam `AuditableModelSerializer` ou `ModelSerializer`
- [ ] Nenhuma FK para `auth_user` nos models de `acoes_pngi`
- [ ] Nenhum campo `orgao` em `tblacoes`
- [ ] `pytest apps/acoes_pngi/ -v` sem FAILED
