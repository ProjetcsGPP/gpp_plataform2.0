from django.conf import settings
from django.contrib.auth.models import User
from django.db import models

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
    """Aplicações da plataforma GPP"""
    idaplicacao = models.AutoField(primary_key=True)
    codigointerno = models.CharField(max_length=50, unique=True)
    nomeaplicacao = models.CharField(max_length=200)
    base_url = models.URLField(blank=True, null=True)
    isshowinportal = models.BooleanField(default=True)

    class Meta:
        db_table = "tblaplicacao"
        managed = True
        verbose_name = "Aplicação"
        verbose_name_plural = "Aplicações"

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
    """Classificação do usuário"""
    idclassificacaousuario = models.SmallIntegerField(
        primary_key=True, db_column="idclassificacaousuario"
    )
    strdescricao = models.CharField(max_length=100, db_column="strdescricao")

    class Meta:
        db_table = "tblclassificacaousuario"
        managed = True
        verbose_name = "Classificação de Usuário"
        verbose_name_plural = "Classificações de Usuários"

    def __str__(self):
        return self.strdescricao


# =====================
# USER PROFILE (EXTENSÃO DO auth.User)
# =====================

class UserProfile(models.Model):
    """
    Extensão do User padrão do Django com campos específicos da GPP Platform.
    Relacionamento OneToOne com auth.User.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,  # 'auth.User'
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='profile'
    )

    # Nome completo (opcional, pois auth.User já tem first_name/last_name)
    name = models.CharField(max_length=200, db_column="strnome", blank=True)

    # Campos de negócio (FK para tabelas auxiliares)
    status_usuario = models.ForeignKey(
        StatusUsuario,
        default=get_default_status_usuario,
        on_delete=models.PROTECT,
        db_column="idstatususuario"
    )
    tipo_usuario = models.ForeignKey(
        TipoUsuario,
        default=get_default_tipo_usuario,
        on_delete=models.PROTECT,
        db_column="idtipousuario"
    )
    classificacao_usuario = models.ForeignKey(
        ClassificacaoUsuario,
        default=get_default_classificacao_usuario,
        on_delete=models.PROTECT,
        db_column="idclassificacaousuario"
    )

    # Campos de auditoria
    idusuariocriacao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="idusuariocriacao",
        related_name="profiles_criados"
    )
    idusuarioalteracao = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="idusuarioalteracao",
        related_name="profiles_alterados"
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
# RBAC - ROLES E PERMISSÕES
# =====================

class Role(models.Model):
    """Perfis RBAC por aplicação"""
    aplicacao = models.ForeignKey(
        Aplicacao,
        on_delete=models.CASCADE,
        null=True,
        db_column="aplicacao_id"
    )
    nomeperfil = models.CharField(max_length=100)
    codigoperfil = models.CharField(max_length=100)

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
    """Relacionamento User <-> Role por aplicação"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # 'auth.User'
        on_delete=models.CASCADE
    )
    aplicacao = models.ForeignKey(
        Aplicacao,
        on_delete=models.CASCADE,
        null=True,
        db_column="aplicacao_id"
    )
    role = models.ForeignKey(Role, on_delete=models.CASCADE)

    class Meta:
        db_table = "accounts_userrole"
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=["user", "aplicacao", "role"],
                name="uq_userrole_user_aplicacao_role",
            )
        ]
        verbose_name = "User Role"
        verbose_name_plural = "User Roles"

    def __str__(self):
        return f"{self.user} → {self.aplicacao} ({self.role})"


class Attribute(models.Model):
    """ABAC - Atributos por usuário/aplicação"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # 'auth.User'
        on_delete=models.CASCADE
    )
    aplicacao = models.ForeignKey(
        Aplicacao,
        on_delete=models.SET_NULL,
        null=True,
        db_column="aplicacao_id"
    )
    key = models.CharField(max_length=100)
    value = models.CharField(max_length=255)

    class Meta:
        db_table = "accounts_attribute"
        managed = True
        constraints = [
            models.UniqueConstraint(
                fields=["user", "aplicacao", "key"],
                name="uq_attribute_user_aplicacao_key"
            )
        ]
        verbose_name = "Attribute"
        verbose_name_plural = "Attributes"

    def __str__(self):
        app_code = self.aplicacao.codigointerno if self.aplicacao else "N/A"
        return f"{self.user} / {app_code} / {self.key}={self.value}"
