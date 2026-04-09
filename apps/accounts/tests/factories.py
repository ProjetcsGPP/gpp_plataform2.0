"""
factories.py
============

Helpers de criação de objetos para os testes do sistema de permissões GPP.
Implementado com Django ORM puro — sem dependências externas (factory_boy).

Regras fundamentais (ADR-PERM-01)
----------------------------------
- NENHUM helper popula ``auth_user_groups`` diretamente.
- ``make_user_role`` e ``make_user_permission_override`` disparam
  ``sync_user_permissions`` após a criação para garantir que
  ``auth_user_user_permissions`` está materializado ao retornar.
- A única fonte de verdade em runtime é ``auth_user_user_permissions``.

Funções disponíveis
--------------------
  make_permission(**kwargs)               — cria/obtém Permission
  make_user(**kwargs)                     — usuário ativo + UserProfile
  make_role(**kwargs)                     — role com Group e Aplicacao
  make_user_role(user, role, **kwargs)    — UserRole + sync automático
  make_user_permission_override(          — Override grant/revoke + sync
      user, permission, mode, **kwargs)

Uso básico
----------
  user = make_user()                          # sem role
  user = make_user(username='joao')           # sobrescreve campo
  role = make_role()                          # nova role em nova aplicacao
  ur   = make_user_role(user=user)            # atribui role ao user + sync
  ov   = make_user_permission_override(       # override de revoke
             user=user,
             permission=perm,
             mode='revoke',
         )
"""

import itertools
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
# Contadores de sequência (substituem factory.Sequence)
# ---------------------------------------------------------------------------
_perm_seq = itertools.count(1)
_user_seq = itertools.count(1)
_role_seq = itertools.count(1)


# ---------------------------------------------------------------------------
# Helpers internos de lookup-tables
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
# make_permission
# ---------------------------------------------------------------------------

def make_permission(
    codename: str | None = None,
    name: str | None = None,
    content_type=None,
) -> Permission:
    """
    Cria ou obtém um ``django.contrib.auth.Permission``.

    Idempotente: se ``codename`` + ``content_type`` já existir, retorna o
    existente sem criar duplicata.

    Parâmetros
    ----------
    codename      : str, opcional  — padrão sequencial ``test_perm_N``
    name          : str, opcional  — padrão derivado do codename
    content_type  : ContentType, opcional — padrão ContentType de ``User``

    Exemplo::

        perm = make_permission(codename='can_do_something')
    """
    if content_type is None:
        content_type = ContentType.objects.get_for_model(User)
    if codename is None:
        codename = f"test_perm_{next(_perm_seq)}"
    if name is None:
        name = f"Test permission {codename}"

    perm, _ = Permission.objects.get_or_create(
        codename=codename,
        content_type=content_type,
        defaults={"name": name},
    )
    return perm


# ---------------------------------------------------------------------------
# make_user
# ---------------------------------------------------------------------------

def make_user(
    username: str | None = None,
    email: str | None = None,
    password: str = "TestPass@2026",
    is_active: bool = True,
    is_superuser: bool = False,
    **extra_fields,
) -> User:
    """
    Cria um ``auth.User`` ativo com ``UserProfile`` associado.

    Não atribui nenhuma role nem popula ``auth_user_groups`` (ADR-PERM-01).
    ``auth_user_user_permissions`` começa vazio — use ``make_user_role`` ou
    ``make_user_permission_override`` para materializar permissões.

    Exemplo::

        user = make_user()                       # username único seqüencial
        user = make_user(username='maria')       # username fixo
        user = make_user(is_superuser=True)      # superuser
    """
    if username is None:
        username = f"test_user_{next(_user_seq)}"
    if email is None:
        email = f"{username}@test.gpp.br"

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        is_active=is_active,
        is_superuser=is_superuser,
        **extra_fields,
    )

    UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "name": username,
            "status_usuario": _get_or_create_status_ativo(),
            "tipo_usuario": _get_or_create_tipo_interno(),
            "classificacao_usuario": _get_or_create_classificacao_padrao(),
        },
    )
    return user


# ---------------------------------------------------------------------------
# make_role
# ---------------------------------------------------------------------------

def make_role(
    codigoperfil: str | None = None,
    nomeperfil: str | None = None,
    group: Group | None = None,
    aplicacao: Aplicacao | None = None,
) -> Role:
    """
    Cria uma ``Role`` com ``Group`` e ``Aplicacao`` associados.

    Cria automaticamente um novo ``auth.Group`` e uma nova ``Aplicacao`` se
    não forem fornecidos. Não popula ``auth_group_permissions`` — isso é
    responsabilidade do teste que precisar de permissões específicas.

    Para criar com permissões::

        perm = make_permission(codename='view_user')
        role = make_role()
        role.group.permissions.add(perm)
    """
    n = next(_role_seq)
    if codigoperfil is None:
        codigoperfil = f"TEST_ROLE_{n}"
    if nomeperfil is None:
        nomeperfil = f"Role {codigoperfil}"
    if group is None:
        group, _ = Group.objects.get_or_create(
            name=f"group_{codigoperfil.lower()}"
        )
    if aplicacao is None:
        aplicacao, _ = Aplicacao.objects.get_or_create(
            codigointerno=f"APP_{codigoperfil}",
            defaults={
                "nomeaplicacao": f"App {codigoperfil}",
                "isappbloqueada": False,
                "isappproductionready": True,
            },
        )

    role, _ = Role.objects.get_or_create(
        codigoperfil=codigoperfil,
        defaults={
            "nomeperfil": nomeperfil,
            "group": group,
            "aplicacao": aplicacao,
        },
    )
    return role


# ---------------------------------------------------------------------------
# make_user_role
# ---------------------------------------------------------------------------

def make_user_role(
    user: User | None = None,
    role: Role | None = None,
) -> UserRole:
    """
    Associa um ``User`` a uma ``Role`` via ``UserRole`` e dispara
    ``sync_user_permissions`` após a criação.

    Garante que ``auth_user_user_permissions`` está materializado ao
    retornar, sem necessidade de chamada manual no ``setUp``.
    Não popula ``auth_user_groups`` (ADR-PERM-01).

    Uso básico::

        ur = make_user_role()                     # cria user e role novos
        ur = make_user_role(user=meu_user)        # reutiliza user existente
        ur = make_user_role(role=role_especifica) # reutiliza role existente

    Verificar permissões após create::

        ur = make_user_role(user=user, role=role_com_perms)
        assert user.user_permissions.exists()     # já materializado
    """
    if user is None:
        user = make_user()
    if role is None:
        role = make_role()

    ur, _ = UserRole.objects.get_or_create(
        user=user,
        aplicacao=role.aplicacao,
        defaults={"role": role},
    )

    from apps.accounts.services.permission_sync import sync_user_permissions
    sync_user_permissions(user)
    return ur


# ---------------------------------------------------------------------------
# make_user_permission_override
# ---------------------------------------------------------------------------

def make_user_permission_override(
    user: User | None = None,
    permission: Permission | None = None,
    mode: str = "grant",
    source: str = "manual",
    reason: str = "",
) -> UserPermissionOverride:
    """
    Cria um ``UserPermissionOverride`` (grant ou revoke) e dispara
    ``sync_user_permissions`` após a criação.

    Garante que ``auth_user_user_permissions`` reflete o override
    imediatamente ao retornar. Não popula ``auth_user_groups`` (ADR-PERM-01).

    Parâmetros
    ----------
    mode   : ``'grant'`` (padrão) ou ``'revoke'``
    source : origem do override (padrão: ``'manual'``)
    reason : motivo do override (padrão: ``''``)

    Uso::

        # Grant extra além das roles
        ov = make_user_permission_override(user=user, permission=perm)

        # Revoke de permissão herdada
        ov = make_user_permission_override(
            user=user,
            permission=perm_herdada,
            mode='revoke',
            reason='Bloqueado por auditoria',
        )
    """
    if user is None:
        user = make_user()
    if permission is None:
        permission = make_permission()

    override, _ = UserPermissionOverride.objects.get_or_create(
        user=user,
        permission=permission,
        defaults={"mode": mode, "source": source, "reason": reason},
    )

    from apps.accounts.services.permission_sync import sync_user_permissions
    sync_user_permissions(user)
    return override


# ---------------------------------------------------------------------------
# Aliases de compatibilidade (uso: make_* como nomes antigos XxxFactory)
# ---------------------------------------------------------------------------
# Permitem chamar make_permission() em vez de PermissionFactory() nos testes
# que ainda usam o estilo antigo, sem precisar alterar os imports.
PermissionFactory = make_permission
UserFactory = make_user
RoleFactory = make_role
UserRoleFactory = make_user_role
UserPermissionOverrideFactory = make_user_permission_override
