"""
GPP Plataform 2.0 — Accounts Serializers
FASE 6: adicionado MeSerializer
GAP-01: adicionado UserCreateSerializer
GAP-02: adicionado AplicacaoSerializer
GAP-03: RoleSerializer enriquecido com campos de aplicacao e group
GAP-04: UserRoleSerializer.validate() — unicidade (user, aplicacao) + role pertence à app
FASE 6: adicionado UserCreateWithRoleSerializer — fluxo orquestrado atômico
FIX: FK fallback via filter().first() + ValidationError 400 explícito (elimina DoesNotExist → 500)
FIX: prints de debug removidos
POLICY-EXPANSION: AplicacaoSerializer expõe os três flags; UserCreateWithRoleSerializer
                  filtra por isappbloqueada=False + isappproductionready=True (R-02).
FASE-0: GPPTokenObtainPairSerializer removido — JWT eliminado do fluxo de autenticação.
ARCH-01: AplicacaoPublicaSerializer — endpoint público expõe apenas codigointerno +
         nomeaplicacao, sem vazar flags internos nem idaplicacao (PK interna).
FASE-4-PERM: UserCreateWithRoleSerializer.create() usa sync_user_permissions() —
             orquestrador idempotente com substituição completa (corrige D-04).
FASE-4-PERM: MePermissionSerializer.get_granted() lê de user.user_permissions
             filtrado pelos codenames do grupo da role (corrige D-02).
FIX-PERMISSIONS-ADDED: UserCreateWithRoleSerializer.create() agora inclui
             permissions_added no dict de retorno — count calculado via
             calculate_effective_permissions() antes do sync.
FASE-7 (Issue #20): UserPermissionOverrideSerializer criado — resolve ImportError
             crítico que quebrava o URL routing completo do Django e derrubava
             ~135 testes. Expõe campos completos do model UserPermissionOverride
             com validação de conflito grant/revoke no nível DRF (400).
"""
import logging

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone as dj_timezone
from rest_framework import serializers

from .services.permission_sync import sync_user_permissions, calculate_effective_permissions

from .models import (
    Aplicacao,
    Attribute,
    ClassificacaoUsuario,
    Role,
    StatusUsuario,
    TipoUsuario,
    UserPermissionOverride,
    UserProfile,
    UserRole,
)

security_logger = logging.getLogger("gpp.security")


# ─── Helpers internos ────────────────────────────────────────────────────────────────────

def _get_fk_or_400(model, pk, field_name):
    """
    Busca instância por PK via filter().first().
    Lança ValidationError 400 explícito se não encontrada,
    evitando DoesNotExist não tratado → 500.
    """
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        raise serializers.ValidationError(
            {field_name: f"Registro com pk={pk} não encontrado."}
        )
    return obj


# ─── Aplicacao Publica (login) ────────────────────────────────────────────────────

class AplicacaoPublicaSerializer(serializers.ModelSerializer):
    """
    ARCH-01 — Serializer público para o endpoint de autenticação.

    Expõe apenas o mínimo necessário para o seletor de app_context
    na tela de login. Não vaza flags internos (isappbloqueada,
    isappproductionready, base_url, isshowinportal) nem PKs internas
    (idaplicacao).

    Endpoint: GET /api/accounts/auth/aplicacoes/
    Acesso: AllowAny
    """

    class Meta:
        model = Aplicacao
        fields = ["codigointerno", "nomeaplicacao"]


# ─── Aplicacao (autenticado) ──────────────────────────────────────────────────────

class AplicacaoSerializer(serializers.ModelSerializer):
    """
    GAP-02 — Serializer autenticado para o model Aplicacao.
    Expõe os três flags de estado para que o frontend decida visibilidade
    e habilitação de ações sem requisições adicionais.

    Endpoint: GET /api/accounts/aplicacoes/
    Acesso: IsAuthenticated (escopo por UserRole ou PORTAL_ADMIN)
    """

    class Meta:
        model = Aplicacao
        fields = [
            "idaplicacao",
            "codigointerno",
            "nomeaplicacao",
            "base_url",
            "isshowinportal",
            "isappbloqueada",
            "isappproductionready",
        ]


# ─── UserProfile ────────────────────────────────────────────────────────────────────────

class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "user_id", "username", "email", "name",
            "status_usuario", "tipo_usuario", "classificacao_usuario",
            "orgao", "datacriacao", "data_alteracao",
        ]
        read_only_fields = ["user_id", "datacriacao", "data_alteracao"]


# ─── UserCreate ─────────────────────────────────────────────────────────────────────────

class UserCreateSerializer(serializers.Serializer):
    """
    GAP-01 — Criação atômica de auth.User + UserProfile.
    Apenas PORTAL_ADMIN pode acionar este serializer (garantido na view).
    """
    # ── Campos auth.User ──────────────────────────────────────────────────
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    first_name = serializers.CharField(max_length=150, required=False, default="")
    last_name = serializers.CharField(max_length=150, required=False, default="")

    # ── Campos UserProfile ──────────────────────────────────────────────────
    name = serializers.CharField(max_length=200)
    orgao = serializers.CharField(max_length=100)
    status_usuario = serializers.IntegerField(required=False, default=1)
    tipo_usuario = serializers.IntegerField(required=False, default=1)
    classificacao_usuario = serializers.IntegerField(required=False, default=1)

    # ── Saída (read) ──────────────────────────────────────────────────────
    user_id = serializers.IntegerField(read_only=True, source="user.id")
    datacriacao = serializers.DateTimeField(read_only=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Este username já está em uso.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Este e-mail já está em uso.")
        return value

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate(self, data):
        for field, model in [
            ("status_usuario", StatusUsuario),
            ("tipo_usuario", TipoUsuario),
            ("classificacao_usuario", ClassificacaoUsuario),
        ]:
            pk = data.get(field, 1)
            if not model.objects.filter(pk=pk).exists():
                raise serializers.ValidationError(
                    {field: f"Registro com pk={pk} não encontrado."}
                )
        return data

    def create(self, validated_data):
        request = self.context["request"]
        with transaction.atomic():
            user = User.objects.create_user(
                username=validated_data["username"],
                email=validated_data["email"],
                password=validated_data["password"],
                first_name=validated_data.get("first_name", ""),
                last_name=validated_data.get("last_name", ""),
            )
            profile = UserProfile.objects.create(
                user=user,
                name=validated_data["name"],
                orgao=validated_data["orgao"],
                status_usuario_id=validated_data.get("status_usuario", 1),
                tipo_usuario_id=validated_data.get("tipo_usuario", 1),
                classificacao_usuario_id=validated_data.get("classificacao_usuario", 1),
                idusuariocriacao=request.user,
            )
        return profile

    def to_representation(self, instance):
        return {
            "user_id": instance.user_id,
            "username": instance.user.username,
            "email": instance.user.email,
            "name": instance.name,
            "orgao": instance.orgao,
            "status_usuario": instance.status_usuario_id,
            "tipo_usuario": instance.tipo_usuario_id,
            "classificacao_usuario": instance.classificacao_usuario_id,
            "datacriacao": instance.datacriacao,
        }


# ─── Role ───────────────────────────────────────────────────────────────────────────────

class RoleSerializer(serializers.ModelSerializer):
    """
    GAP-03 — Serializer enriquecido de Role.
    """
    aplicacao_id     = serializers.IntegerField(source="aplicacao.idaplicacao", read_only=True)
    aplicacao_codigo = serializers.CharField(source="aplicacao.codigointerno", read_only=True)
    aplicacao_nome   = serializers.CharField(source="aplicacao.nomeaplicacao", read_only=True)
    group_id         = serializers.IntegerField(source="group.id", read_only=True, allow_null=True)
    group_name       = serializers.CharField(source="group.name", read_only=True, allow_null=True)

    class Meta:
        model = Role
        fields = [
            "id",
            "nomeperfil",
            "codigoperfil",
            "aplicacao_id",
            "aplicacao_codigo",
            "aplicacao_nome",
            "group_id",
            "group_name",
        ]


# ─── UserRole ─────────────────────────────────────────────────────────────────────────

class UserRoleSerializer(serializers.ModelSerializer):
    """
    GAP-04 — Validações de negócio:
    R-01: unicidade por (user, aplicacao).
    R-02: a role atribuída deve pertencer à aplicacao informada.
    """
    role_codigo = serializers.CharField(source="role.codigoperfil", read_only=True)
    aplicacao_codigo = serializers.CharField(source="aplicacao.codigointerno", read_only=True)

    class Meta:
        model = UserRole
        fields = ["id", "user", "aplicacao", "aplicacao_codigo", "role", "role_codigo"]

    def validate(self, data):
        user = data.get("user")
        aplicacao = data.get("aplicacao")
        role = data.get("role")

        already_exists = UserRole.objects.filter(
            user=user,
            aplicacao=aplicacao,
        ).exists()
        if already_exists:
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        f"O usuário '{user.username}' já possui uma role "
                        f"na aplicação '{aplicacao.codigointerno}'. "
                        "Remova a role atual antes de atribuir uma nova."
                    ]
                }
            )

        if role.aplicacao != aplicacao:
            raise serializers.ValidationError(
                {"role": "A role selecionada não pertence à aplicação informada."}
            )

        return data


# ─── UserCreateWithRole ───────────────────────────────────────────────────────────────

class UserCreateWithRoleSerializer(serializers.Serializer):
    """
    FASE 6 — Criação atômica de auth.User + UserProfile + UserRole + sync de permissões.
    FASE 4 — usa sync_user_permissions() (orquestrador idempotente) em vez de
             sync_user_permissions_from_group() (incremental).
    FIX     — retorna permissions_added: int com o total de permissões materializadas
              para o novo usuário. Calculado via calculate_effective_permissions()
              antes do sync para evitar dupla chamada ao banco.
    """

    username   = serializers.CharField(max_length=150)
    email      = serializers.EmailField()
    password   = serializers.CharField(write_only=True, style={"input_type": "password"})
    first_name = serializers.CharField(max_length=150, required=False, default="")
    last_name  = serializers.CharField(max_length=150, required=False, default="")

    name     = serializers.CharField(max_length=200)
    orgao    = serializers.CharField(max_length=100)
    status_usuario = serializers.PrimaryKeyRelatedField(
        queryset=StatusUsuario.objects.all(), required=False
    )
    tipo_usuario = serializers.PrimaryKeyRelatedField(
        queryset=TipoUsuario.objects.all(), required=False
    )
    classificacao_usuario = serializers.PrimaryKeyRelatedField(
        queryset=ClassificacaoUsuario.objects.all(), required=False
    )

    aplicacao_id = serializers.PrimaryKeyRelatedField(
        queryset=Aplicacao.objects.filter(
            isappbloqueada=False,
            isappproductionready=True,
        ),
        source="aplicacao",
    )
    role_id = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(),
        source="role",
    )

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Este username já está em uso.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Este e-mail já está em uso.")
        return value

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate(self, data):
        aplicacao = data.get("aplicacao")
        role = data.get("role")

        if role and aplicacao and role.aplicacao != aplicacao:
            raise serializers.ValidationError(
                {"role_id": "A role não pertence à aplicação informada."}
            )

        if data.get("status_usuario") is None:
            _get_fk_or_400(StatusUsuario, 1, "status_usuario")
        if data.get("tipo_usuario") is None:
            _get_fk_or_400(TipoUsuario, 1, "tipo_usuario")
        if data.get("classificacao_usuario") is None:
            _get_fk_or_400(ClassificacaoUsuario, 1, "classificacao_usuario")

        return data

    def create(self, validated_data):
        request   = self.context["request"]
        aplicacao = validated_data["aplicacao"]
        role      = validated_data["role"]

        status_usuario        = validated_data.get("status_usuario") or StatusUsuario.objects.get(pk=1)
        tipo_usuario          = validated_data.get("tipo_usuario") or TipoUsuario.objects.get(pk=1)
        classificacao_usuario = validated_data.get("classificacao_usuario") or ClassificacaoUsuario.objects.get(pk=1)

        with transaction.atomic():
            user = User.objects.create_user(
                username=validated_data["username"],
                email=validated_data["email"],
                password=validated_data["password"],
                first_name=validated_data.get("first_name", ""),
                last_name=validated_data.get("last_name", ""),
            )

            profile = UserProfile.objects.create(
                user=user,
                name=validated_data["name"],
                orgao=validated_data["orgao"],
                status_usuario=status_usuario,
                tipo_usuario=tipo_usuario,
                classificacao_usuario=classificacao_usuario,
                idusuariocriacao=request.user,
            )

            UserRole.objects.create(
                user=user,
                aplicacao=aplicacao,
                role=role,
            )

            # Calcula o conjunto efetivo ANTES do sync para expor o count
            # na resposta sem precisar de uma segunda consulta após o set().
            effective_perms = calculate_effective_permissions(user)
            permissions_added = len(effective_perms)

            # Fase 4: sync completo via orquestrador idempotente
            sync_user_permissions(user)

        return {
            "user_id":            user.id,
            "username":           user.username,
            "email":              user.email,
            "name":               profile.name,
            "orgao":              profile.orgao,
            "aplicacao":          aplicacao.codigointerno,
            "role":               role.codigoperfil,
            "datacriacao":        profile.datacriacao,
            "permissions_added":  permissions_added,
        }


# ─── UserPermissionOverride ───────────────────────────────────────────────────────────

class UserPermissionOverrideSerializer(serializers.ModelSerializer):
    """
    FASE-7 (Issue #20) — Serializer para UserPermissionOverride.

    Resolve o ImportError crítico que impedia o carregamento de views.py
    e quebrava o URL routing completo do Django (~135 testes afetados).

    Campos expostos:
      - id              : PK do override (read_only via ModelSerializer)
      - user            : FK para auth.User (PK inteira)
      - permission      : FK para auth.Permission (PK inteira)
      - mode            : 'grant' | 'revoke'
      - source          : origem do override (ex: 'admin manual') — opcional
      - reason          : justificativa para auditoria — opcional
      - created_at      : timestamp de criação (read_only)
      - updated_at      : timestamp da última atualização (read_only)
      - created_by      : usuário que criou (read_only — preenchido pela view via AuditableMixin)
      - updated_by      : último usuário que atualizou (read_only — idem)

    Validação:
      validate() impede coexistência de override 'grant' e 'revoke' para o
      mesmo par (user, permission), espelhando o clean() do model em nível DRF
      para garantir resposta 400 em vez de exceção não tratada.

    Referências: ADR-PERM-01, divergência D-04, Issue #18, Issue #20.
    """

    class Meta:
        model = UserPermissionOverride
        fields = [
            "id",
            "user",
            "permission",
            "mode",
            "source",
            "reason",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "created_by", "updated_by"]

    def validate(self, data):
        user = data.get("user") or (self.instance.user if self.instance else None)
        permission = data.get("permission") or (self.instance.permission if self.instance else None)
        mode = data.get("mode") or (self.instance.mode if self.instance else None)

        if user and permission and mode:
            opposite_mode = (
                UserPermissionOverride.MODE_REVOKE
                if mode == UserPermissionOverride.MODE_GRANT
                else UserPermissionOverride.MODE_GRANT
            )
            conflict_qs = UserPermissionOverride.objects.filter(
                user=user,
                permission=permission,
                mode=opposite_mode,
            )
            if self.instance:
                conflict_qs = conflict_qs.exclude(pk=self.instance.pk)
            if conflict_qs.exists():
                raise serializers.ValidationError(
                    {
                        "mode": (
                            f"Já existe um override '{opposite_mode}' para este usuário e permissão. "
                            "Remova o override conflitante antes de criar um novo."
                        )
                    }
                )

        return data


# ─── Me Serializer ────────────────────────────────────────────────────────────────────

class UserRoleNestedSerializer(serializers.ModelSerializer):
    role_codigo = serializers.CharField(source="role.codigoperfil", read_only=True)
    role_nome = serializers.CharField(source="role.nomeperfil", read_only=True)
    aplicacao_codigo = serializers.CharField(source="aplicacao.codigointerno", read_only=True)
    aplicacao_nome = serializers.CharField(source="aplicacao.nomeaplicacao", read_only=True)

    class Meta:
        model = UserRole
        fields = ["id", "aplicacao_codigo", "aplicacao_nome", "role_codigo", "role_nome"]


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="user.id")
    username = serializers.CharField(source="user.username")
    email = serializers.EmailField(source="user.email")
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    is_portal_admin = serializers.SerializerMethodField()

    name = serializers.SerializerMethodField()
    orgao = serializers.SerializerMethodField()
    status_usuario_id = serializers.SerializerMethodField()

    roles = UserRoleNestedSerializer(source="user_roles", many=True)

    def get_is_portal_admin(self, obj):
        return UserRole.objects.filter(
            user=obj["user"],
            role__codigoperfil="PORTAL_ADMIN",
        ).exists()

    def get_name(self, obj):
        profile = obj.get("profile")
        return profile.name if profile else None

    def get_orgao(self, obj):
        profile = obj.get("profile")
        return profile.orgao if profile else None

    def get_status_usuario_id(self, obj):
        profile = obj.get("profile")
        return profile.status_usuario_id if profile else None


class MePermissionSerializer(serializers.Serializer):
    """
    Serializer para GET /api/accounts/me/permissions/?app=<codigo>
    Retorna a role do usuário na app e os codenames de permissão concedidos.

    Formato:
    {
        "role": "GESTOR",
        "granted": ["view_programa", "add_programa"]
    }

    Espera receber o dict:
    {
        "role": <instância Role>,
        "user": <instância User>,
    }

    FASE-4-PERM (corrige D-02):
        A leitura agora é feita diretamente de ``user.user_permissions``
        (``auth_user_user_permissions``), filtrada pelos codenames do grupo
        da role para manter o escopo por aplicação.
        Isso garante que as permissões retornadas sejam consistentes com
        o que ``AuthorizationService.can()`` e ``HasRolePermission`` enxergam.
    """
    role = serializers.SerializerMethodField()
    granted = serializers.SerializerMethodField()

    def get_role(self, obj):
        return obj["role"].codigoperfil

    def get_granted(self, obj):
        user = obj["user"]
        role = obj["role"]
        group = role.group

        if group is None:
            # Role sem grupo: retorna todas as permissões diretas do usuário
            return list(
                user.user_permissions
                .values_list("codename", flat=True)
                .order_by("codename")
            )

        # Obtém os codenames que o grupo define para esta role
        group_codenames = set(
            group.permissions.values_list("codename", flat=True)
        )

        # Retorna apenas as permissões do usuário que pertencem ao escopo
        # desta role — leitura exclusiva de auth_user_user_permissions (D-02)
        return list(
            user.user_permissions
            .filter(codename__in=group_codenames)
            .values_list("codename", flat=True)
            .order_by("codename")
        )
