# common/admin_config.py
from django.contrib.admin.apps import AdminConfig


class PortalAdminConfig(AdminConfig):
    default_site = "common.admin_site.PortalAdminSite"
