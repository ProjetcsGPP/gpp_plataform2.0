from django.contrib import admin
from django.contrib.auth.models import User

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
    AccountsSession,
)


# =====================
# TABELAS AUXILIARES
# =====================

@admin.register(StatusUsuario)
class StatusUsuarioAdmin(admin.ModelAdmin):
    list_display = ("idstatususuario", "strdescricao")
    search_fields = ("strdescricao",)
    ordering = ("idstatususuario",)


@admin.register(TipoUsuario)
class TipoUsuarioAdmin(admin.ModelAdmin):
    list_display = ("idtipousuario", "strdescricao")
    search_fields = ("strdescricao",)
    ordering = ("idtipousuario",)


@admin.register(ClassificacaoUsuario)
class ClassificacaoUsuarioAdmin(admin.ModelAdmin):
    list_display = ("idclassificacaousuario", "strdescricao")
    search_fields = ("strdescricao",)
    ordering = ("idclassificacaousuario",)


@admin.register(Aplicacao)
class AplicacaoAdmin(admin.ModelAdmin):
    list_display = ("codigointerno", "nomeaplicacao", "base_url", "isshowinportal")
    list_filter = ("isshowinportal",)
    search_fields = ("codigointerno", "nomeaplicacao")
    ordering = ("codigointerno",)


# =====================
# USER PROFILE
# =====================

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "name",
        "status_usuario",
        "tipo_usuario",
        "classificacao_usuario",
        "orgao",
    )
    list_filter = ("status_usuario", "tipo_usuario", "classificacao_usuario")
    search_fields = ("user__username", "user__email", "name", "orgao")
    readonly_fields = ("datacriacao", "data_alteracao", "idusuariocriacao", "idusuarioalteracao")
    fieldsets = (
        ("Identificação", {
            "fields": ("user", "name", "orgao"),
        }),
        ("Classificações", {
            "fields": ("status_usuario", "tipo_usuario", "classificacao_usuario"),
        }),
        ("Auditoria", {
            "classes": ("collapse",),
            "fields": ("idusuariocriacao", "idusuarioalteracao", "datacriacao", "data_alteracao"),
        }),
    )


# =====================
# RBAC
# =====================

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("codigoperfil", "nomeperfil", "aplicacao", "group")
    list_filter = ("aplicacao",)
    search_fields = ("codigoperfil", "nomeperfil")
    ordering = ("aplicacao", "codigoperfil")
    readonly_fields = ("group",)
    fieldsets = (
        (None, {
            "fields": ("aplicacao", "codigoperfil", "nomeperfil"),
        }),
        ("Grupo Django (gerado automaticamente)", {
            "classes": ("collapse",),
            "description": (
                "O auth.Group é criado automaticamente via signal ao salvar uma Role "
                "sem group definido. Gerencie as permissões do grupo diretamente no "
                "admin de Grupos do Django."
            ),
            "fields": ("group",),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields
        return ()


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "aplicacao", "role", "get_group")
    list_filter = ("aplicacao", "role__aplicacao")
    search_fields = ("user__username", "user__email", "role__codigoperfil")
    ordering = ("user__username", "aplicacao")

    @admin.display(description="Grupo Django (auth.Group)")
    def get_group(self, obj):
        return obj.role.group if obj.role else "-"


# =====================
# ABAC — Atributos
# =====================

@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ("user", "aplicacao", "key", "value")
    list_filter = ("aplicacao",)
    search_fields = ("user__username", "key", "value")
    ordering = ("user__username", "aplicacao", "key")


# =====================
# SESSION (sessão Django)
# =====================

@admin.register(AccountsSession)
class AccountsSessionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "session_key_short",
        "app_context",
        "ip_address",
        "created_at",
        "expires_at",
        "revoked",
    )
    list_filter = ("revoked", "app_context")
    search_fields = ("user__username", "session_key", "ip_address", "app_context")
    readonly_fields = (
        "user",
        "session_key",
        "app_context",
        "created_at",
        "expires_at",
        "ip_address",
        "user_agent",
        "revoked_at",
    )
    ordering = ("-created_at",)
    actions = ["revoke_sessions"]

    @admin.display(description="Session Key")
    def session_key_short(self, obj):
        return f"{obj.session_key[:12]}..."

    @admin.action(description="Revogar sessões selecionadas")
    def revoke_sessions(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(revoked=False).update(
            revoked=True,
            revoked_at=timezone.now(),
        )
        self.message_user(request, f"{updated} sessão(ões) revogada(s) com sucesso.")


# =====================
# PERMISSION OVERRIDES (Fase 3)
# =====================

@admin.register(UserPermissionOverride)
class UserPermissionOverrideAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "permission",
        "mode",
        "source",
        "created_by",
        "created_at",
        "updated_at",
    )
    list_filter = ("mode",)
    search_fields = (
        "user__username",
        "user__email",
        "permission__codename",
        "permission__content_type__app_label",
        "source",
    )
    ordering = ("user__username", "permission__codename", "mode")
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")
    fieldsets = (
        ("Override", {
            "fields": ("user", "permission", "mode"),
        }),
        ("Contexto", {
            "fields": ("source", "reason"),
        }),
        ("Auditoria", {
            "classes": ("collapse",),
            "fields": ("created_by", "updated_by", "created_at", "updated_at"),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
