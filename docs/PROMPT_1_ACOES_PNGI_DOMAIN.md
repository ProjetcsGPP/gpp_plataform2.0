# PROMPT 1 — Domínio acoes_pngi: Models, Serializers e ViewSets

**Pré-requisito**: leia `docs/ARCH_SNAPSHOT.md` antes de executar.

---

## Objetivo

Implementar o domínio completo de `acoes_pngi`:
1. Corrigir os 3 gaps no `models.py`
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

### SecureQuerysetMixin
Toda ViewSet que expõe recursos de usuário **deve** herdar
`SecureQuerysetMixin`. Ele filtra o queryset por `orgao`
(campo no model) = `request.user.profile.orgao` (campo no UserProfile).
**Acoes precisa ter campo `orgao`** para que isso funcione.

### AuditableModelSerializer
Disponível em `common/serializers.py`. Todos os serializers de
`acoes_pngi` devem herdar dele:
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

### 1.1 Adicionar `orgao` a `Acoes`

Campo obrigatório para o `SecureQuerysetMixin` funcionar:

```python
# Em Acoes:
orgao = models.CharField(
    max_length=100,
    db_column="orgao",
    help_text="Código do órgão responsável. Escopo de IDOR — preenchido no create via request.user.profile.orgao."
)
```

### 1.2 Conectar `Acoes` a `SituacaoAcao`

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

### 1.3 Conectar `Acoes` a `Eixo`

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
Models de referência (sem `AuditableModel`) usam `ModelSerializer` simples.

### Serializers necessários:

```
EixoSerializer              → Eixo
SituacaoAcaoSerializer      → SituacaoAcao
VigenciaPNGISerializer      → VigenciaPNGI
TipoEntraveAlertaSerializer → TipoEntraveAlerta
AcoesSerializer             → Acoes  (principal)
AcaoPrazoSerializer         → AcaoPrazo
AcaoDestaqueSerializer      → AcaoDestaque
AcaoAnotacaoAlinhamentoSerializer → AcaoAnotacaoAlinhamento
```

### Regras de serialização para `AcoesSerializer`:
- `idacao`, `strapelido`, `strdescricaoacao`, `strdescricaoentrega`,
  `datdataentrega`, `orgao` — leitura e escrita
- `idvigenciapngi`, `idtipoentravealerta`, `idsituacaoacao`, `ideixo` — write como PK int
- Campos de auditoria — herdados de `AuditableModelSerializer` (read-only)
- `orgao` deve ser **read-only no serializer** e preenchido na view via `perform_create`

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
class AcaoViewSet(SecureQuerysetMixin, AuditableMixin, viewsets.ModelViewSet):
    queryset = Acoes.objects.select_related(
        "idvigenciapngi", "idtipoentravealerta", "idsituacaoacao", "ideixo"
    )
    serializer_class = AcoesSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]
    scope_field = "orgao"     # campo em Acoes
    scope_source = "orgao"    # campo em UserProfile

    def perform_create(self, serializer):
        # Herdar de AuditableMixin e adicionar orgao:
        user = self.request.user
        name = user.get_full_name().strip() or user.username
        serializer.save(
            orgao=user.profile.orgao,
            created_by_id=user.pk,
            created_by_name=name,
            updated_by_id=user.pk,
            updated_by_name=name,
        )
```

### Manter `_load_role_matrix()` do scaffold:

A função `_load_role_matrix()` com `lru_cache(maxsize=1)` que já existe
no scaffold está correta e deve ser mantida. Ela carrega as roles do banco
**uma vez por processo** sem string hardcoded.

---

## Passo 4 — Migration

Após editar `models.py`, gerar a migration:

```bash
python manage.py makemigrations acoes_pngi \
    --name add_orgao_situacao_eixo_to_acoes
```

Após gerar, verificar se a migration:
- Adiciona `orgao` como `VARCHAR(100) NOT NULL` (definir default para migration)
- Adiciona `idsituacaoacao_id` como FK nullable para `tblsituacaoacao`
- Adiciona `ideixo_id` como FK nullable para `tbleixos`
- **Não cria FK para `auth_user`** em nenhum campo

---

## Critérios de Conclusão

- [ ] `makemigrations` sem warnings
- [ ] `migrate` aplica sem erro
- [ ] `AcaoPNGIViewSet` (agora `AcaoViewSet`) funcional com queryset real
- [ ] Todos os serializers herdam `AuditableModelSerializer` ou `ModelSerializer`
- [ ] Nenhuma FK para `auth_user` nos models de `acoes_pngi`
- [ ] `pytest apps/acoes_pngi/ -v` sem FAILED
