"""
GPP Plataform 2.0 — Accounts Serializers
FASE 6: adicionado MeSerializer
GAP-01: adicionado UserCreateSerializer
GAP-02: adicionado AplicacaoSerializer
GAP-03: RoleSerializer enriquecido com campos de aplicacao e group
"""
import logging

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Aplicacao, Attribute, Role, UserProfile, UserRole

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
    role_codigo = serializers.CharField(source="role.codigoperfil", read_only=True)
    aplicacao_codigo = serializers.CharField(source="aplicacao.codigointerno", read_only=True)

    class Meta:
        model = UserRole
        fields = ["id", "user", "aplicacao", "aplicacao_codigo", "role", "role_codigo"]


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
