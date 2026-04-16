"""
GPP Plataform 2.0 — Accounts Models

Estrutura:
- Aplicacao         : aplicações da plataforma (tblaplicacao)
- StatusUsuario     : status do usuário
- TipoUsuario       : tipo do usuário
- ClassificacaoUsuario
- UserProfile       : extensão do auth.User (tblusuario)
- Role              : perfis RBAC por aplicação — com FK para auth_group
- UserRole          : relação User <-> Role por aplicação
- Attribute         : atributos ABAC por usuário/aplicação
- AccountsSession   : sessões ativas baseadas em session_key Django (anti-replay, auditoria)
- UserPermissionOverride : overrides individuais de permissão (grant/revoke) — Fase 3

FASE-0: AccountsSession refatorada — jti removido; session_key + app_context adicionados.
FASE-3: UserPermissionOverride adicionado — camada explícita de exceções individuais
        sem edição direta de auth_user_user_permissions.
FIX: Aplicacao.save() normaliza codigointerno para maiúsculas antes de persistir.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


def get_default_status_usuario():
    return StatusUsuario.objects.get(pk=1)


def get_default_tipo_usuario():
    return TipoUsuario.objects.get(pk=1)


def get_default_classificacao_usuario():
    return ClassificacaoUsuario.objects.get(pk=1)


# =====================
# TABELAS AUXILIARES
# =====================


class Aplicacao(models.Model):
    """Aplicações da plataforma GPP."""

    idaplicacao = models.AutoField(primary_key=True)
    codigointerno = models.CharField(max_length=50, unique=True)
    nomeaplicacao = models.CharField(max_length=200)
    base_url = models.URLField(blank=True, null=True)
    isshowinportal = models.BooleanField(default=True)
    isappbloqueada = models.BooleanField(
        default=False,
        null=True,
        db_column="isappbloqueada",
        help_text=(
            "Indica se a aplicação está bloqueada para uso. "
            "Quando True, nenhum usuário (exceto PORTAL_ADMIN ou SuperUser) "
            "pode ter novos vínculos criados nesta aplicação. "
            "Uma app pode estar bloqueada por manutenção, auditoria ou incidente "
            "independentemente do seu estado de produção."
        ),
    )
    isappproductionready = models.BooleanField(
        default=False,
        null=True,
        db_column="isappproductionready",
        help_text=(
            "Indica se a aplicação está homologada e habilitada para uso "
            "em ambiente de produção. Somente apps com este flag True "
            "e isappbloqueada=False aceitam novos vínculos de usuários. "
            "O tratamento de visibilidade no portal é feito no frontend."
        ),
    )

    class Meta:
        db_table = "tblaplicacao"
        managed = True
        verbose_name = "Aplicação"
        verbose_name_plural = "Aplicações"

    def save(self, *args, **kwargs):
        # Garante que codigointerno seja sempre persistido em maiúsculas,
        # independentemente do casing informado pelo usuário/admin.
        if self.codigointerno:
            self.codigointerno = self.codigointerno.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigointerno} - {self.nomeaplicacao}"


class StatusUsuario(models.Model):
    """Status do usuário (Ativo, Inativo, etc.)"""

    idstatususuario = models.SmallIntegerField(
        primary_key=True, db_column="idstatususuario"
    )
    strdescricao = models.CharField(max_length=100, db_column="strdescricao")

    class Meta:
        db_table = "tblstatususuario"
        managed = True
        verbose_name = "Status de Usuário"
        verbose_name_plural = "Status de Usuários"

    def __str__(self):
        return self.strdescricao


class TipoUsuario(models.Model):
    """Tipo de usuário (Gestor, Técnico, etc.)"""

    idtipousuario = models.SmallIntegerField(
        primary_key=True, db_column="idtipousuario"
    )
    strdescricao = models.CharField(max_length=100, db_column="strdescricao")

    class Meta:
        db_table = "tbltipousuario"
        managed = True
        verbose_name = "Tipo de Usuário"
        verbose_name_plural = "Tipos de Usuários"

    def __str__(self):
        return self.strdescricao


class ClassificacaoUsuario(models.Model):
    """
    Classificação do usuário.

    Os campos pode_criar_usuario e pode_editar_usuario controlam
    autorização de gerenciamento de usuários na plataforma.
    São lidos pelo AuthorizationService — nunca por hard code de role.
    """

    idclassificacaousuario = models.SmallIntegerField(
        primary_key=True, db_column="idclassificacaousuario"
    )
    strdescricao = models.CharField(max_length=100, db_column="strdescricao")
    pode_criar_usuario = models.BooleanField(
        default=False,
        db_column="pode_criar_usuario",
        help_text="Permite criar novos usuários na plataforma.",
    )
    pode_editar_usuario = models.BooleanField(
        default=False,
        db_column="pode_editar_usuario",
        help_text="Permite editar usuários existentes na plataforma.",
    )

    class Meta:
        db_table = "tblclassificacaousuario"
        managed = True
        verbose_name = "Classificação de Usuário"
        verbose_name_plural = "Classificações de Usuários"

    def __str__(self):
        return self.strdescricao


# =====================
# USER PROFILE
# =====================


class UserProfile(models.Model):
    """
    Extensão do User padrão do Django com campos específicos da GPP Platform.
    Relacionamento OneToOne com auth.User.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="profile",
    )
    name = models.CharField(max_length=200, db_column="strnome", blank=True)
    status_usuario = models.ForeignKey(
        StatusUsuario,
        default=get_default_status_usuario,
        on_delete=models.PROTECT,
        db_column="idstatususuario",
    )
    tipo_usuario = models.ForeignKey(
        TipoUsuario,
        default=get_default_tipo_usuario,
        on_delete=models.PROTECT,
        db_column="idtipousuario",
    )
    classificacao_usuario = models.ForeignKey(
        ClassificacaoUsuario,
        default=get_default_classificacao_usuario,
        on_delete=models.PROTECT,
        db_column="idclassificacaousuario",
    )
    # Campo de escopo para proteção IDOR — filtrado em SecureQuerysetMixin
    orgao = models.CharField(max_length=100, blank=True, null=True, db_column="orgao")

    # Auditoria
    idusuariocriacao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="idusuariocriacao",
        related_name="profiles_criados",
    )
    idusuarioalteracao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="idusuarioalteracao",
        related_name="profiles_alterados",
    )
    datacriacao = models.DateTimeField(auto_now_add=True, db_column="datacriacao")
    data_alteracao = models.DateTimeField(
        null=True, blank=True, auto_now=True, db_column="data_alteracao"
    )

    class Meta:
        db_table = "tblusuario"
        managed = True
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"Profile de {self.user.username} ({self.user.email})"


# =====================
# RBAC
# =====================


class Role(models.Model):
    """
    Perfis RBAC por aplicação.
    A FK 'group' liga diretamente ao auth_group do Django,
    eliminando a dependência de sincronização por nome.
    """

    aplicacao = models.ForeignKey(
        Aplicacao,
        on_delete=models.CASCADE,
        null=True,
        db_column="aplicacao_id",
    )
    nomeperfil = models.CharField(max_length=100)
    codigoperfil = models.CharField(max_length=100)
    group = models.ForeignKey(
        "auth.Group",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="roles",
        help_text="Grupo Django correspondente. Criado automaticamente via signal se não informado.",
    )

    class Meta:
        db_table = "accounts_role"
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=["aplicacao", "codigoperfil"],
                name="uq_role_aplicacao_codigoperfil",
            )
        ]
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self):
        return f"{self.aplicacao} / {self.codigoperfil}"


class UserRole(models.Model):
    """Relacionamento User <-> Role por aplicação."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    aplicacao = models.ForeignKey(
        Aplicacao,
        on_delete=models.CASCADE,
        null=True,
        db_column="aplicacao_id",
    )
    role = models.ForeignKey(Role, on_delete=models.CASCADE)

    class Meta:
        db_table = "accounts_userrole"
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=["user", "aplicacao"],
                name="uq_userrole_user_aplicacao",
            )
        ]
        verbose_name = "User Role"
        verbose_name_plural = "User Roles"

    def __str__(self):
        return f"{self.user} → {self.aplicacao} ({self.role})"


class Attribute(models.Model):
    """ABAC — Atributos por usuário/aplicação."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    aplicacao = models.ForeignKey(
        Aplicacao,
        on_delete=models.SET_NULL,
        null=True,
        db_column="aplicacao_id",
    )
    key = models.CharField(max_length=100)
    value = models.CharField(max_length=255)

    class Meta:
        db_table = "accounts_attribute"
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=["user", "aplicacao", "key"],
                name="uq_attribute_user_aplicacao_key",
            )
        ]
        verbose_name = "Attribute"
        verbose_name_plural = "Attributes"

    def __str__(self):
        app_code = self.aplicacao.codigointerno if self.aplicacao else "N/A"
        return f"{self.user} / {app_code} / {self.key}={self.value}"


# =====================
# SESSION (stateful — session_key Django)
# =====================


class AccountsSession(models.Model):
    """
    Representa uma sessão autenticada do usuário baseada em session_key do Django.

    Substitui o uso de JWT (jti), permitindo controle stateful de sessões,
    revogação e auditoria de acesso por aplicação (app_context).

    Campos:
      session_key  — request.session.session_key do Django
      app_context  — codigointerno da aplicação (ex: PORTAL, ACOES_PNGI)
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account_sessions",
    )

    session_key = models.CharField(
        max_length=40,
        db_index=True,
        help_text="Chave da sessão Django (request.session.session_key)",
    )

    app_context = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Código interno da aplicação (ex: PORTAL, ACOES_PNGI)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    expires_at = models.DateTimeField()

    revoked = models.BooleanField(default=False)

    revoked_at = models.DateTimeField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)

    user_agent = models.TextField(blank=True, default="")

    session_cookie_name = models.CharField(
        max_length=100, null=True, blank=True, default="\\"
    )

    class Meta:
        db_table = "accounts_session"
        managed = True
        verbose_name = "Session"
        verbose_name_plural = "Sessions"
        indexes = [
            models.Index(fields=["session_key", "revoked"]),
            models.Index(fields=["user", "revoked"]),
            models.Index(fields=["session_cookie_name"]),
        ]

    def revoke(self):
        """Revoga a sessão."""
        if not self.revoked:
            self.revoked = True
            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked", "revoked_at"])

    def __str__(self):
        return f"{self.user_id} - {self.session_key} - {self.app_context}"


# =====================
# PERMISSION OVERRIDES (Fase 3)
# =====================


class UserPermissionOverride(models.Model):
    """
    Representa um override individual de permissão para um usuário específico.

    Permite adicionar (grant) ou remover (revoke) permissões em relação
    ao conjunto herdado pela role do usuário, sem editar diretamente
    as tabelas auth_user_user_permissions ou auth_user_groups.

    Regras de negócio:
    - ``grant``: concede uma permissão que o usuário não herdaria pela role.
    - ``revoke``: retira uma permissão que a role concederia ao usuário.
    - Não é permitida duplicidade por ``(user, permission, mode)``.
    - Não é permitida coexistência de ``grant`` e ``revoke`` para o mesmo
      par ``(user, permission)`` — constraint ``uq_override_no_conflict``.

    Referências:
    - ADR-PERM-01 (docs/PERMISSIONS_ARCHITECTURE.md)
    - Divergência D-04: overrides manuais não rastreados (pré-Fase 3)
    """

    MODE_GRANT = "grant"
    MODE_REVOKE = "revoke"
    MODE_CHOICES = [
        (MODE_GRANT, "Grant — conceder permissão extra"),
        (MODE_REVOKE, "Revoke — retirar permissão da role"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="permission_overrides",
        help_text="Usuário ao qual o override se aplica.",
    )
    permission = models.ForeignKey(
        "auth.Permission",
        on_delete=models.CASCADE,
        related_name="user_overrides",
        help_text="Permissão Django (auth.Permission) que está sendo sobrescrita.",
    )
    mode = models.CharField(
        max_length=6,
        choices=MODE_CHOICES,
        help_text=(
            "'grant' adiciona a permissão ao usuário independentemente da role. "
            "'revoke' retira a permissão mesmo que a role a conceda."
        ),
    )
    source = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Origem do override (ex: 'admin manual', 'integração XPTO'). Opcional.",
    )
    reason = models.TextField(
        blank=True,
        default="",
        help_text="Justificativa detalhada para o override. Opcional, mas recomendada para auditoria.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="overrides_criados",
        help_text="Usuário que criou o override (auditoria).",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="overrides_atualizados",
        help_text="Último usuário a atualizar o override (auditoria).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_userpermissionoverride"
        managed = True
        verbose_name = "User Permission Override"
        verbose_name_plural = "User Permission Overrides"
        constraints = [
            # Impede duplicidade de (user, permission, mode)
            models.UniqueConstraint(
                fields=["user", "permission", "mode"],
                name="uq_userpermoverride_user_permission_mode",
            ),
            # Impede coexistência de grant e revoke para o mesmo par (user, permission)
            # Implementado via unique_together parcial: garantido em nível de aplicação
            # pela validação no clean() e reforçado pela constraint acima (mode distinto).
            # Uma constraint de banco completa exigiria CHECK/EXCLUDE (PostgreSQL) —
            # a validação em clean() é a camada primária de proteção.
        ]
        indexes = [
            models.Index(fields=["user", "mode"]),
            models.Index(fields=["permission"]),
        ]

    def clean(self):
        """
        Impede coexistência de grant e revoke para o mesmo par (user, permission).

        Levanta ValidationError se já existir um override com o modo oposto
        para o mesmo usuário e permissão.
        """
        from django.core.exceptions import ValidationError

        opposite_mode = (
            self.MODE_REVOKE if self.mode == self.MODE_GRANT else self.MODE_GRANT
        )
        conflict_qs = UserPermissionOverride.objects.filter(
            user=self.user,
            permission=self.permission,
            mode=opposite_mode,
        )
        if self.pk:
            conflict_qs = conflict_qs.exclude(pk=self.pk)
        if conflict_qs.exists():
            raise ValidationError(
                f"Já existe um override '{opposite_mode}' para este usuário e permissão. "
                "Remova o override conflitante antes de criar um novo."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} | {self.permission.codename} | {self.mode}"


class UserAuthzState(models.Model):
    """
    Estado de versionamento de autorização por usuário.

    Mantém um contador (authz_version) que é incrementado sempre que
    o conjunto de permissões do usuário muda. O frontend usa este valor
    para decidir se deve refazer o fetch de permissões.

    Regras:
      - Relação 1:1 com auth.User.
      - Persistido em banco — não depende de Redis.
      - Sobrevive restart de servidor.
      - NÃO é fonte de verdade de permissões — apenas invalidador.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="authz_state",
    )
    authz_version = models.BigIntegerField(
        default=0,
        help_text=(
            "Contador de versão de autorização. Incrementado atomicamente "
            "a cada mudança de permissão. Usado APENAS pelo frontend para "
            "invalidação de cache — não representa permissões reais."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_userauthzstate"
        managed = True
        verbose_name = "User AuthZ State"
        verbose_name_plural = "User AuthZ States"

    def __str__(self):
        return f"AuthZState(user_id={self.user_id}, version={self.authz_version})"
