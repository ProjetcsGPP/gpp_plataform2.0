"""Testes de views: cargas."""

import pytest

from apps.carga_org_lot.tests.view_helpers import (CARGAS_URL, HISTORICO_URL,
                                                   PATRIARCAS_URL)


@pytest.mark.django_db(transaction=True)
class TestCargaEHistorico:
    def test_crud_carga_sem_expor_token(
        self,
        client_gestor_carga_lot,
        tipo_organograma,
        status_processando,
    ):
        create_response = client_gestor_carga_lot.post(
            CARGAS_URL,
            {
                "strtoken": "segredo",
                "idtipocarga_id": tipo_organograma.pk,
                "idstatusprogresso_id": status_processando.pk,
            },
            format="json",
        )
        assert create_response.status_code == 201
        pk = create_response.data["idtokenenviocarga"]
        assert create_response.data["possui_token"] is True
        assert "strtoken" not in create_response.data

        assert client_gestor_carga_lot.get(CARGAS_URL).status_code == 200
        assert client_gestor_carga_lot.get(f"{CARGAS_URL}{pk}/").status_code == 200
        assert (
            client_gestor_carga_lot.patch(
                f"{CARGAS_URL}{pk}/",
                {"idstatusprogresso_id": status_processando.pk},
                format="json",
            ).status_code
            == 200
        )
        assert client_gestor_carga_lot.delete(f"{CARGAS_URL}{pk}/").status_code == 204

    def test_crud_historico(
        self,
        client_gestor_carga_lot,
        carga,
        status_carga_recebida,
    ):
        create_response = client_gestor_carga_lot.post(
            HISTORICO_URL,
            {
                "idtokenenviocarga_id": carga.pk,
                "idstatuscarga_id": status_carga_recebida.pk,
                "strmensagem": "Arquivo recebido.",
            },
            format="json",
        )
        assert create_response.status_code == 201
        pk = create_response.data["iddetalhestatuscarga"]

        assert client_gestor_carga_lot.get(HISTORICO_URL).status_code == 200
        assert client_gestor_carga_lot.get(f"{HISTORICO_URL}{pk}/").status_code == 200
        patch_response = client_gestor_carga_lot.patch(
            f"{HISTORICO_URL}{pk}/",
            {"strmensagem": "Atualizado."},
            format="json",
        )
        assert patch_response.status_code == 200
        assert patch_response.data["strmensagem"] == "Atualizado."
        assert (
            client_gestor_carga_lot.delete(f"{HISTORICO_URL}{pk}/").status_code == 204
        )


@pytest.mark.django_db(transaction=True)
class TestAutorizacao:
    def test_portal_admin_pode_listar(self, client_portal_admin):
        assert client_portal_admin.get(PATRIARCAS_URL).status_code == 200

    def test_sem_role_e_negado(self, client_sem_role_carga):
        response = client_sem_role_carga.get(PATRIARCAS_URL)
        assert response.status_code in (401, 403)
