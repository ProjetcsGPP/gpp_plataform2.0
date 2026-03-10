from django.contrib import admin
from .models import (
    Aplicacao, StatusUsuario, TipoUsuario, ClassificacaoUsuario,
    UserProfile, Role, UserRole, Attribute, AccountsSession,
)


@admin.register(Aplicacao)
class AplicacaoAdmin(admin.ModelAdmin):
    list_display = ("codigointerno", "nomeaplicacao", "isshowinportal")
    search_fields = ("codigointerno", "nomeaplicacao")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("codigoperfil", "nomeperfil", "aplicacao", "group")
    list_filter = ("aplicacao",)
    search_fields = ("codigoperfil", "nomeperfil")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "aplicacao", "role")
    list_filter = ("aplicacao", "role")
    search_fields = ("user__username",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "status_usuario", "tipo_usuario")
    search_fields = ("user__username", "user__email", "name")


@admin.register(AccountsSession)
class AccountsSessionAdmin(admin.ModelAdmin):
    list_display = ("user", "jti", "created_at", "revoked")
    list_filter = ("revoked",)
    search_fields = ("user__username", "jti")
    actions = ["revoke_sessions"]

    @admin.action(description="Revogar sessões selecionadas")
    def revoke_sessions(self, request, queryset):
        queryset.update(revoked=True)


admin.site.register(StatusUsuario)
admin.site.register(TipoUsuario)
admin.site.register(ClassificacaoUsuario)
admin.site.register(Attribute)
