"""
GPP Plataform 2.0 — Ações PNGI
Todos os models usam schema 'acoes_pngi' no PostgreSQL.
"""
from common.models import AuditableModel

# Models serão implementados na fase de domínio da app.
# Exemplo de como declarar com schema próprio:
#
# class AcaoPNGI(AuditableModel):
#     ...
#     class Meta:
#         db_table = '"acoes_pngi"."tblacao"'
#         managed = True
