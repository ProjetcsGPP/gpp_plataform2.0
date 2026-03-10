"""
GPP Plataform 2.0 — Accounts Serializers
"""
import logging

from django.contrib.auth.models import User
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

        # Valida UserProfile ativo
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

        # Valida ao menos 1 UserRole
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
        # Claims extras (não usar para autorização — sempre validar no banco)
        token["username"] = user.username
        token["email"] = user.email
        is_admin = UserRole.objects.filter(
            user=user, role__codigoperfil="PORTAL_ADMIN"
        ).exists()
        token["is_portal_admin"] = is_admin
        return token


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


# ─── Role ──────────────────────────────────────────────────────────────────────────

class RoleSerializer(serializers.ModelSerializer):
    aplicacao_codigo = serializers.CharField(source="aplicacao.codigointerno", read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True)

    class Meta:
        model = Role
        fields = ["id", "aplicacao", "aplicacao_codigo", "nomeperfil", "codigoperfil", "group", "group_name"]


# ─── UserRole ──────────────────────────────────────────────────────────────────────

class UserRoleSerializer(serializers.ModelSerializer):
    role_codigo = serializers.CharField(source="role.codigoperfil", read_only=True)
    aplicacao_codigo = serializers.CharField(source="aplicacao.codigointerno", read_only=True)

    class Meta:
        model = UserRole
        fields = ["id", "user", "aplicacao", "aplicacao_codigo", "role", "role_codigo"]
