"""
GPP Plataform 2.0 — Database Router
Roteia cada app para o banco/schema correto.
Atualmente todos no mesmo PostgreSQL (schemas via db_table nos models).
Prepara para separação futura de infraestrutura.
"""


class SchemaRouter:
    """
    Roteador de banco de dados por app_label.
    Todas as apps usam o banco 'default' (PostgreSQL único),
    mas os models de acoes_pngi e carga_org_lot usam
    db_table com schema qualificado: '"schema"."tabela"'.
    """

    APP_DB_MAP = {
        "accounts": "default",
        "portal": "default",
        "acoes_pngi": "default",
        "carga_org_lot": "default",
        "common": "default",
        # Quando a infraestrutura separar:
        # "acoes_pngi": "acoes_pngi_db",
        # "carga_org_lot": "carga_org_lot_db",
    }

    def db_for_read(self, model, **hints):
        return self.APP_DB_MAP.get(model._meta.app_label, "default")

    def db_for_write(self, model, **hints):
        return self.APP_DB_MAP.get(model._meta.app_label, "default")

    def allow_relation(self, obj1, obj2, **hints):
        """Permite relações entre objetos do mesmo banco."""
        db1 = self.APP_DB_MAP.get(obj1._meta.app_label, "default")
        db2 = self.APP_DB_MAP.get(obj2._meta.app_label, "default")
        return db1 == db2

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Cada app só migra para seu banco correspondente."""
        target = self.APP_DB_MAP.get(app_label, "default")
        return db == target
