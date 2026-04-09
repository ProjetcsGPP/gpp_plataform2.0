"""
factories.py
============

Factories para os testes do sistema de permissões GPP.
Criadas com factory_boy para uso em toda a suíte de testes.

Regras fundamentais (ADR-PERM-01)
----------------------------------
- NENHUMA factory popula ``auth_user_groups`` diretamente.
- ``UserRoleFactory`` e ``UserPermissionOverrideFactory`` disparam
  ``sync_user_permissions`` no ``_after_create`` para garantir que
  ``auth_user_user_permissions`` está materializado ao sair do ``create()``.
- A única fonte de verdade em runtime é ``auth_user_user_permissions``.

Factories disponíveis
---------------------
  PermissionFactory                — cria ``django.contrib.auth.Permission``
  UserFactory                      — usuário básico + UserProfile, sem role
  RoleFactory                      — role com Group associado a uma Aplicacao
  UserRoleFactory                  — associa UserFactory a RoleFactory + sync
  UserPermissionOverrideFactory    — cria override grant/revoke + sync

Uso básico
----------
  user = UserFactory()                        # sem role
  user = UserFactory(username='joao')         # sobrescreve campo
  role = RoleFactory()                        # nova role em nova aplicacao
  ur   = UserRoleFactory(user=user)           # atribui role ao user, chama sync
  ov   = UserPermissionOverrideFactory(       # override de revoke
             user=user,
             mode='revoke',
         )
"""

import factory
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType

from apps.accounts.models import (
    Aplicacao,
    ClassificacaoUsuario,
    Role,
    StatusUsuario,
    TipoUsuario,
    UserPermissionOverride,
    UserProfile,
    UserRole,
)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _get_or_create_status_ativo():
    obj, _ = StatusUsuario.objects.get_or_create(
        pk=1, defaults={"strdescricao": "Ativo"}
    )
    return obj


def _get_or_create_tipo_interno():
    obj, _ = TipoUsuario.objects.get_or_create(
        pk=1, defaults={"strdescricao": "Interno"}
    )
    return obj


def _get_or_create_classificacao_padrao():
    obj, _ = ClassificacaoUsuario.objects.get_or_create(
        pk=1,
        defaults={
            "strdescricao": "Usuario Padrao",
            "pode_criar_usuario": False,
            "pode_editar_usuario": False,
        },
    )
    return obj


# ---------------------------------------------------------------------------
# PermissionFactory
# ---------------------------------------------------------------------------

class PermissionFactory(factory.django.DjangoModelFactory):
    """
    Cria um ``django.contrib.auth.Permission`` para uso em overrides e testes.

    Por padrão usa o ContentType de ``User``. Pode ser sobrescrito passando
    ``content_type=...`` explicitamente.

    Exemplo::

        perm = PermissionFactory(codename='can_do_something')
        perm = PermissionFactory(
            codename='view_report',
            name='Can view report',
            content_type=ContentType.objects.get_for_model(MyModel),
        )
    """

    class Meta:
        model = Permission
        django_get_or_create = ("codename", "content_type")

    codename = factory.Sequence(lambda n: f"test_perm_{n}")
    name = factory.LazyAttribute(lambda obj: f"Test permission {obj.codename}")
    content_type = factory.LazyFunction(
        lambda: ContentType.objects.get_for_model(User)
    )


# ---------------------------------------------------------------------------
# UserFactory
# ---------------------------------------------------------------------------

class UserFactory(factory.django.DjangoModelFactory):
    """
    Cria um ``auth.User`` ativo com ``UserProfile`` associado.

    Não atribui nenhuma role nem popula ``auth_user_groups`` (ADR-PERM-01).
    ``auth_user_user_permissions`` começa vazio — use ``UserRoleFactory`` ou
    ``UserPermissionOverrideFactory`` para materializar permissões.

    Exemplo::

        user = UserFactory()                          # username único seqüencial
        user = UserFactory(username='maria')          # username fixo
        user = UserFactory(is_superuser=True)         # superuser
    """

    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"test_user_{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@test.gpp.br")
    is_active = True
    is_superuser = False

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):  # noqa: N805
        raw = extracted or "TestPass@2026"
        obj.set_password(raw)
        if create:
            obj.save(update_fields=["password"])

    @factory.post_generation
    def _create_profile(obj, create, extracted, **kwargs):  # noqa: N805
        if not create:
            return
        UserProfile.objects.get_or_create(
            user=obj,
            defaults={
                "name": obj.username,
                "status_usuario": _get_or_create_status_ativo(),
                "tipo_usuario": _get_or_create_tipo_interno(),
                "classificacao_usuario": _get_or_create_classificacao_padrao(),
            },
        )


# ---------------------------------------------------------------------------
# RoleFactory
# ---------------------------------------------------------------------------

class RoleFactory(factory.django.DjangoModelFactory):
    """
    Cria uma ``Role`` com ``Group`` associado a uma ``Aplicacao``.

    Cria automaticamente um novo ``auth.Group`` e uma nova ``Aplicacao`` se
    não forem fornecidos. Não popula ``auth_group_permissions`` — isso é
    responsabilidade do teste que precisar de permissões específicas.

    Para criar uma role sobre uma aplicacao existente::

        app = Aplicacao.objects.get(codigointerno='ACOES_PNGI')
        role = RoleFactory(aplicacao=app)

    Para criar com permissões::

        perm = PermissionFactory(codename='view_user')
        role = RoleFactory()
        role.group.permissions.add(perm)
    """

    class Meta:
        model = Role
        django_get_or_create = ("codigoperfil",)

    codigoperfil = factory.Sequence(lambda n: f"TEST_ROLE_{n}")
    nomeperfil = factory.LazyAttribute(lambda obj: f"Role {obj.codigoperfil}")
    group = factory.LazyAttribute(
        lambda obj: Group.objects.get_or_create(
            name=f"group_{obj.codigoperfil.lower()}"
        )[0]
    )
    aplicacao = factory.LazyAttribute(
        lambda obj: Aplicacao.objects.get_or_create(
            codigointerno=f"APP_{obj.codigoperfil}",
            defaults={
                "nomeaplicacao": f"App {obj.codigoperfil}",
                "isappbloqueada": False,
                "isappproductionready": True,
            },
        )[0]
    )


# ---------------------------------------------------------------------------
# UserRoleFactory
# ---------------------------------------------------------------------------

class UserRoleFactory(factory.django.DjangoModelFactory):
    """
    Associa um ``User`` a uma ``Role`` via ``UserRole`` e dispara
    ``sync_user_permissions`` no ``_after_create``.

    Garante que ``auth_user_user_permissions`` está materializado ao sair
    do ``create()``, sem necessidade de chamada manual no ``setUp``.
    Não popula ``auth_user_groups`` (ADR-PERM-01).

    Uso básico::

        ur = UserRoleFactory()                       # cria user e role novos
        ur = UserRoleFactory(user=meu_user)          # reutiliza user existente
        ur = UserRoleFactory(role=role_especifica)   # reutiliza role existente

    Verificar permissões após create::

        ur = UserRoleFactory(user=user, role=role_com_perms)
        assert user.user_permissions.exists()        # já materializado
    """

    class Meta:
        model = UserRole
        django_get_or_create = ("user", "aplicacao")

    user = factory.SubFactory(UserFactory)
    role = factory.SubFactory(RoleFactory)
    aplicacao = factory.LazyAttribute(lambda obj: obj.role.aplicacao)

    @classmethod
    def _after_postgeneration(cls, instance, create, results=None):
        """
        Materializa auth_user_user_permissions após criação da UserRole.
        Chamado automaticamente pelo factory_boy após todos os post_generation.
        """
        if not create:
            return
        from apps.accounts.services.permission_sync import sync_user_permissions
        sync_user_permissions(instance.user)


# ---------------------------------------------------------------------------
# UserPermissionOverrideFactory
# ---------------------------------------------------------------------------

class UserPermissionOverrideFactory(factory.django.DjangoModelFactory):
    """
    Cria um ``UserPermissionOverride`` (grant ou revoke) e dispara
    ``sync_user_permissions`` no ``_after_create``.

    Garante que ``auth_user_user_permissions`` reflete o override imediatamente
    após o ``create()``.
    Não popula ``auth_user_groups`` (ADR-PERM-01).

    Parâmetros-chave:
        mode (str): ``'grant'`` (padrão) ou ``'revoke'``
        source (str): origem do override (padrão: ``'manual'``)
        reason (str): motivo do override (padrão: ``''``)

    Uso::

        # Grant extra além das roles
        ov = UserPermissionOverrideFactory(user=user, permission=perm)

        # Revoke de permissão herdada
        ov = UserPermissionOverrideFactory(
            user=user,
            permission=perm_herdada,
            mode='revoke',
            reason='Bloqueado por auditoria',
        )
    """

    class Meta:
        model = UserPermissionOverride
        django_get_or_create = ("user", "permission")

    user = factory.SubFactory(UserFactory)
    permission = factory.SubFactory(PermissionFactory)
    mode = "grant"
    source = "manual"
    reason = ""

    @classmethod
    def _after_postgeneration(cls, instance, create, results=None):
        """
        Re-materializa auth_user_user_permissions após criação do override.
        """
        if not create:
            return
        from apps.accounts.services.permission_sync import sync_user_permissions
        sync_user_permissions(instance.user)
