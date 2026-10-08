# common/admin_site.py
from django.contrib import admin
from django.utils.text import slugify


class PortalAdminSite(admin.AdminSite):
    site_header = "Administração do Site"
    site_title = "Administração do Site"

    # Apps cujos models serão reagrupados. Os demais ficam como estão.
    REGROUP_APPS = {"accounts", "auth"}

    GROUPS = [
        (
            "Usuários",
            [
                "auth.user",
                "accounts.userprofile",
                "accounts.statususuario",
                "accounts.tipousuario",
                "accounts.classificacaousuario",
            ],
        ),
        (
            "Autorização (RBAC/ABAC)",
            [
                "accounts.role",
                "accounts.userrole",
                "auth.group",
                "accounts.userpermissionoverride",
                "accounts.attribute",
            ],
        ),
        (
            "Aplicações e Navegação",
            [
                "accounts.aplicacao",
                "accounts.capability",
                "accounts.rolecapability",
                "accounts.menu",
            ],
        ),
        (
            "Auditoria e Sessões",
            [
                "accounts.accountssession",
                "accounts.userauthzstate",
            ],
        ),
    ]

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        if app_label:  # página interna de um app: mantém o padrão
            return app_list

        # Separa os models que serão reagrupados dos apps que ficam intactos
        models, untouched = {}, []
        for app in app_list:
            if app["app_label"] in self.REGROUP_APPS:
                for m in app["models"]:
                    key = f'{app["app_label"]}.{m["object_name"].lower()}'
                    models[key] = m
            else:
                untouched.append(app)

        result, used = [], set()
        for title, keys in self.GROUPS:
            items = [models[k] for k in keys if k in models]
            used.update(k for k in keys if k in models)
            if items:
                result.append(self._block(title, items))

        # Rede de segurança: nada some se não estiver em GROUPS
        rest = [m for k, m in models.items() if k not in used]
        if rest:
            result.append(self._block("Outros", rest))

        return result + untouched

    @staticmethod
    def _block(title, items):
        return {
            "name": title,
            "app_label": slugify(title),
            "app_url": "",  # bloco misto: sem link no título
            "has_module_perms": True,
            "models": items,
        }
