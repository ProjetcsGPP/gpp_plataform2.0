"""
GPP Plataform 2.0 — Accounts Serializers
FASE 6: adicionado MeSerializer
GAP-01: adicionado UserCreateSerializer
GAP-02: adicionado AplicacaoSerializer
GAP-03: RoleSerializer enriquecido com campos de aplicacao e group
GAP-04: UserRoleSerializer.validate() — unicidade (user, aplicacao) + role pertence à app
FASE 6: adicionado UserCreateWithRoleSerializer — fluxo orquestrado atômico
"""
import logging

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone as dj_timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Aplicacao,
    Attribute,
    ClassificacaoUsuario,
    Role,
    StatusUsuario,
    TipoUsuario,
    UserProfile,
    UserRole,
)

security_logger = logging.getLogger("gpp.security")


# ─── JWT Token Serializer customizado ─────────────────────────────────────────────────

class GPPTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializer de login customizado.
    Valida:
    1. Credenciais (username/password) — herdado do pai
    2. UserProfile ativo (status_usuario = 1)
    3. Ao menos 1 UserRole ativa
    Adiciona claims extras ao token: user_id, username, is_portal_admin.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        try:
            profile = user.profile
            if profile.status_usuario_id != 1:
                security_logger.warning(
                    "LOGIN_FAILURE username=%s reason=inactive_profile",
                    user.username,
                )
                raise serializers.ValidationError(
                    "Usuário inativo. Entre em contato com o administrador."
                )
        except UserProfile.DoesNotExist:
            security_logger.warning(
                "LOGIN_FAILURE username=%s reason=no_profile",
                user.username,
            )
            raise serializers.ValidationError(
                "Perfil de usuário não encontrado."
            )

        has_role = UserRole.objects.filter(user=user).exists()
        if not has_role:
            security_logger.warning(
                "LOGIN_FAILURE username=%s reason=no_role",
                user.username,
            )
            raise serializers.ValidationError(
                "Usuário sem perfil de acesso. Entre em contato com o administrador."
            )

        security_logger.info(
            "LOGIN_SUCCESS user_id=%s username=%s",
            user.id, user.username,
        )

        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        token["email"] = user.email
        is_admin = UserRole.objects.filter(
            user=user, role__codigoperfil="PORTAL_ADMIN"
        ).exists()
        token["is_portal_admin"] = is_admin
        return token


# ─── Aplicacao ────────────────────────────────────────────────────────────────────────

class AplicacaoSerializer(serializers.ModelSerializer):
    """
    GAP-02 — Serializer somente leitura para o model Aplicacao.
    Expõe apenas campos necessários para associação de usuário.
    isshowinportal NÃO é exposto — o filtro é feito no ViewSet.
    """

    class Meta:
        model = Aplicacao
        fields = ["idaplicacao", "codigointerno", "nomeaplicacao", "base_url"]


# ─── UserProfile ──────────────────────────────────────────────────────────────────────

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


# ─── UserCreate ───────────────────────────────────────────────────────────────────────

class UserCreateSerializer(serializers.Serializer):
    """
    GAP-01 — Criação atômica de auth.User + UserProfile.
    Apenas PORTAL_ADMIN pode acionar este serializer (garantido na view).
    """
    # ── Campos auth.User ──────────────────────────────────────────
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    first_name = serializers.CharField(max_length=150, required=False, default="")
    last_name = serializers.CharField(max_length=150, required=False, default="")

    # ── Campos UserProfile ────────────────────────────────────────
    name = serializers.CharField(max_length=200)
    orgao = serializers.CharField(max_length=100)
    status_usuario = serializers.IntegerField(required=False, default=1)
    tipo_usuario = serializers.IntegerField(required=False, default=1)
    classificacao_usuario = serializers.IntegerField(required=False, default=1)

    # ── Saída (read) ──────────────────────────────────────────────
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
        """Formata a saída a partir de um UserProfile já criado."""
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


# ─── Role ─────────────────────────────────────────────────────────────────────────────

class RoleSerializer(serializers.ModelSerializer):
    """
    GAP-03 — Serializer enriquecido de Role.

    Expõe campos de Aplicacao e auth.Group desaninhados para que o frontend
    possa popular seletores sem requisições extras.

    R-06: campos group_id e group_name são allow_null=True para suportar
    roles legadas criadas antes do signal de auto-criação de group.
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


# ─── UserRole ──────────────────────────────────────────────────────────────────────

class UserRoleSerializer(serializers.ModelSerializer):
    """
    GAP-04 — Validações de negócio:
    R-01: unicidade por (user, aplicacao) — 1 role por app por usuário.
    R-02: a role atribuída deve pertencer à aplicacao informada no payload.
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

        # R-01: unicidade por (user, aplicacao)
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

        # R-02: a role deve pertencer à aplicacao informada
        if role.aplicacao != aplicacao:
            raise serializers.ValidationError(
                {"role": "A role selecionada não pertence à aplicação informada."}
            )

        return data


# ─── UserCreateWithRole ───────────────────────────────────────────────────────────────

class UserCreateWithRoleSerializer(serializers.Serializer):
    """
    FASE 6 — Criação atômica de auth.User + UserProfile + UserRole + sync de permissões.

    Orquestra em uma única transação as operações das Fases 1 e 4.
    Apenas PORTAL_ADMIN pode acionar (garantido na view).

    Validações:
      - Senha via validate_password() (Django)
      - username e email únicos
      - aplicacao_id apenas para apps com isshowinportal=False (R-02)
      - role deve pertencer à aplicacao informada (R-03)
      - unicidade (user, aplicacao) — herdada da lógica da Fase 4 (R-04)

    Retorno:
      dict com user_id, username, email, name, orgao, aplicacao, role,
      permissions_added e datacriacao.
    """

    # ── Campos auth.User ──────────────────────────────────────────
    username   = serializers.CharField(max_length=150)
    email      = serializers.EmailField()
    password   = serializers.CharField(write_only=True, style={"input_type": "password"})
    first_name = serializers.CharField(max_length=150, required=False, default="")
    last_name  = serializers.CharField(max_length=150, required=False, default="")

    # ── Campos UserProfile ────────────────────────────────────────
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

    # ── Campos de associação ──────────────────────────────────────
    # R-02: só aceita apps com isshowinportal=False
    aplicacao_id = serializers.PrimaryKeyRelatedField(
        queryset=Aplicacao.objects.filter(isshowinportal=False),
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

        # R-03: role deve pertencer à aplicacao informada
        if role and aplicacao and role.aplicacao != aplicacao:
            raise serializers.ValidationError(
                {"role_id": "A role não pertence à aplicação informada."}
            )

        return data

    def create(self, validated_data):
        from .services.permission_sync import sync_user_permissions_from_group

        request   = self.context["request"]
        aplicacao = validated_data["aplicacao"]
        role      = validated_data["role"]

        # Defaults para FKs opcionais
        status_usuario        = validated_data.get("status_usuario") or StatusUsuario.objects.get(pk=1)
        tipo_usuario          = validated_data.get("tipo_usuario") or TipoUsuario.objects.get(pk=1)
        classificacao_usuario = validated_data.get("classificacao_usuario") or ClassificacaoUsuario.objects.get(pk=1)

        with transaction.atomic():
            # 1. Criar auth.User
            user = User.objects.create_user(
                username=validated_data["username"],
                email=validated_data["email"],
                password=validated_data["password"],
                first_name=validated_data.get("first_name", ""),
                last_name=validated_data.get("last_name", ""),
            )

            # 2. Criar UserProfile
            profile = UserProfile.objects.create(
                user=user,
                name=validated_data["name"],
                orgao=validated_data["orgao"],
                status_usuario=status_usuario,
                tipo_usuario=tipo_usuario,
                classificacao_usuario=classificacao_usuario,
                idusuariocriacao=request.user,
            )

            # 3. Criar UserRole
            UserRole.objects.create(
                user=user,
                aplicacao=aplicacao,
                role=role,
            )

            # 4. Sincronizar permissões (R-01: rollback total se falhar)
            permissions_added = sync_user_permissions_from_group(
                user=user,
                group=role.group,
            )

        return {
            "user_id":          user.id,
            "username":         user.username,
            "email":            user.email,
            "name":             profile.name,
            "orgao":            profile.orgao,
            "aplicacao":        aplicacao.codigointerno,
            "role":             role.codigoperfil,
            "permissions_added": permissions_added,
            "datacriacao":      profile.datacriacao,
        }


# ─── Me Serializer ────────────────────────────────────────────────────────────────

class UserRoleNestedSerializer(serializers.ModelSerializer):
    """Serializer aninhado de UserRole para o endpoint /me/."""
    role_codigo = serializers.CharField(source="role.codigoperfil", read_only=True)
    role_nome = serializers.CharField(source="role.nomeperfil", read_only=True)
    aplicacao_codigo = serializers.CharField(source="aplicacao.codigointerno", read_only=True)
    aplicacao_nome = serializers.CharField(source="aplicacao.nomeaplicacao", read_only=True)

    class Meta:
        model = UserRole
        fields = ["id", "aplicacao_codigo", "aplicacao_nome", "role_codigo", "role_nome"]


class MeSerializer(serializers.Serializer):
    """
    Serializer composto para GET /api/accounts/me/.
    Agrega: dados do user, profile e roles ativas.
    """
    id = serializers.IntegerField(source="user.id")
    username = serializers.CharField(source="user.username")
    email = serializers.EmailField(source="user.email")
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    is_portal_admin = serializers.SerializerMethodField()

    # Profile fields (nullable caso não exista)
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
