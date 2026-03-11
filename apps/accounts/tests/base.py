# apps/accounts/tests/base.py
from rest_framework.test import APIClient

class DRFTestClient(APIClient):
    """
    Client que usa force_authenticate para bypassar o middleware JWT.
    Uso:
        client = DRFTestClient()
        client.force_authenticate(user=meu_user)
    """
    pass
