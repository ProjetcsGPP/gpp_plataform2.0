from django.contrib import admin
from django.contrib.auth.models import User

from .models import (
    Aplicacao,
    Attribute,
    ClassificacaoUsuario,
    Role,
    StatusUsuario,
    TipoUsuario,
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

# Os inlines precisam ser registrados no admin.ModelAdmin do auth.User,
# pois Attribute e UserRole tem FK para auth.User (nao para UserProfile).
# UserProfileAdmin usa fieldsets e readonly_fields apenas para o perfil em si.

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
# SESSION (anti-replay)
# =====================

@admin.register(AccountsSession)
class AccountsSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "jti_short", "ip_address", "created_at", "expires_at", "revoked")
    list_filter = ("revoked",)
    search_fields = ("user__username", "jti", "ip_address")
    readonly_fields = ("user", "jti", "created_at", "expires_at", "ip_address", "user_agent")
    ordering = ("-created_at",)
    actions = ["revoke_sessions"]

    @admin.display(description="JTI")
    def jti_short(self, obj):
        return f"{obj.jti[:16]}..."

    @admin.action(description="Revogar sessões selecionadas")
    def revoke_sessions(self, request, queryset):
        updated = queryset.update(revoked=True)
        self.message_user(request, f"{updated} sessão(ões) revogada(s) com sucesso.")
