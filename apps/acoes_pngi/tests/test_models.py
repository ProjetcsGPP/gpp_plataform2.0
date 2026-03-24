"""
Testes de constraints e estrutura dos models de acoes_pngi.
Verifica integridade do banco diretamente via SQL.
"""
import pytest
from django.db import connection

from apps.acoes_pngi.models import Acoes, VigenciaPNGI


@pytest.mark.django_db(transaction=True)
def test_acoes_herda_auditablemodel_colunas(db):
    """tblacoes deve ter as 6 colunas de AuditableModel como campos simples."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'acoes_pngi' AND table_name = 'tblacoes'"
        )
        cols = [r[0] for r in cursor.fetchall()]
    assert "created_by_id" in cols
    assert "created_by_name" in cols
    assert "updated_by_id" in cols
    assert "updated_by_name" in cols
    assert "created_at" in cols
    assert "updated_at" in cols


@pytest.mark.django_db(transaction=True)
def test_acoes_sem_fk_para_auth_user(db):
    """tblacoes nao deve ter nenhuma FK referenciando auth_user."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.table_constraints tc
            JOIN information_schema.referential_constraints rc
              ON tc.constraint_name = rc.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON rc.unique_constraint_name = ccu.constraint_name
            WHERE tc.table_schema = 'acoes_pngi'
              AND tc.table_name   = 'tblacoes'
              AND ccu.table_name  = 'auth_user'
        """)
        count = cursor.fetchone()[0]
    assert count == 0, "tblacoes nao deve ter FK para auth_user"


@pytest.mark.django_db(transaction=True)
def test_acoes_possui_fk_idsituacaoacao(db):
    """tblacoes deve ter FK para tblsituacaoacao."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.table_constraints tc
            JOIN information_schema.referential_constraints rc
              ON tc.constraint_name = rc.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON rc.unique_constraint_name = ccu.constraint_name
            WHERE tc.table_schema = 'acoes_pngi'
              AND tc.table_name   = 'tblacoes'
              AND ccu.table_name  = 'tblsituacaoacao'
        """)
        count = cursor.fetchone()[0]
    assert count == 1, "tblacoes deve ter FK para tblsituacaoacao"


@pytest.mark.django_db(transaction=True)
def test_acoes_possui_fk_ideixo(db):
    """tblacoes deve ter FK para tbleixos."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.table_constraints tc
            JOIN information_schema.referential_constraints rc
              ON tc.constraint_name = rc.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON rc.unique_constraint_name = ccu.constraint_name
            WHERE tc.table_schema = 'acoes_pngi'
              AND tc.table_name   = 'tblacoes'
              AND ccu.table_name  = 'tbleixos'
        """)
        count = cursor.fetchone()[0]
    assert count == 1, "tblacoes deve ter FK para tbleixos"


@pytest.mark.django_db(transaction=True)
def test_acoes_sem_campo_orgao(db):
    """tblacoes NAO deve ter campo orgao — acoes sao independentes de orgao."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'acoes_pngi' AND table_name = 'tblacoes'"
        )
        cols = [r[0] for r in cursor.fetchall()]
    assert "orgao" not in cols, "tblacoes nao deve ter campo orgao"


@pytest.mark.django_db(transaction=True)
def test_create_acao_sem_situacao_e_eixo(db, vigencia):
    """Criar Acao sem idsituacaoacao e ideixo deve funcionar (null=True)."""
    acao = Acoes.objects.create(
        strapelido="ACAO-NULL-FK",
        strdescricaoacao="Teste FK nullable",
        strdescricaoentrega="Entrega",
        idvigenciapngi=vigencia,
    )
    assert acao.pk is not None
    assert acao.idsituacaoacao is None
    assert acao.ideixo is None


@pytest.mark.django_db(transaction=True)
def test_create_acao_com_situacao_e_eixo(db, vigencia, situacao, eixo):
    """Criar Acao com FK idsituacaoacao e ideixo preenchidos."""
    acao = Acoes.objects.create(
        strapelido="ACAO-COM-FK",
        strdescricaoacao="Teste FK preenchido",
        strdescricaoentrega="Entrega",
        idvigenciapngi=vigencia,
        idsituacaoacao=situacao,
        ideixo=eixo,
    )
    assert acao.idsituacaoacao_id == situacao.pk
    assert acao.ideixo_id == eixo.pk


@pytest.mark.django_db(transaction=True)
def test_vigenciapngi_herda_auditablemodel(db):
    """VigenciaPNGI deve ter os campos de AuditableModel."""
    v = VigenciaPNGI.objects.create(
        strdescricao="Vigencia Teste",
        datiniciovigencia="2025-01-01",
    )
    assert hasattr(v, "created_by_id")
    assert hasattr(v, "created_by_name")
    assert hasattr(v, "updated_by_id")
    assert hasattr(v, "updated_by_name")
