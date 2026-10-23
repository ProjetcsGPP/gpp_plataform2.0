"""Classificação funcional dos casos de validação de lotação."""

from django.db.models import Q


SUBJECT_LABELS = {
    "CARGO": "Cargo",
    "CPF": "CPF",
    "SERVIDOR": "Servidor",
    "ORGANOGRAMA": "Órgão ou unidade",
    "ARQUIVO": "Arquivo ou planilha",
    "OUTROS": "Outros",
}


def validation_case_subject(code: str) -> str:
    """Retorna uma categoria estável e amigável para a crítica."""
    normalized = (code or "").lower()
    if normalized.startswith("cargo_"):
        return "CARGO"
    if normalized.startswith("cpf_"):
        return "CPF"
    if normalized.startswith("nome_servidor_"):
        return "SERVIDOR"
    if any(token in normalized for token in ("orgao", "unidade", "organograma")):
        return "ORGANOGRAMA"
    if any(token in normalized for token in ("arquivo", "planilha", "cabecalho")):
        return "ARQUIVO"
    return "OUTROS"


def validation_subject_query(subject: str) -> Q:
    """Traduz o assunto público para um filtro seguro de códigos."""
    normalized = (subject or "").strip().upper()
    if normalized not in SUBJECT_LABELS:
        raise ValueError("Assunto de validação inválido.")
    if normalized == "CARGO":
        return Q(strcodigo__istartswith="cargo_")
    if normalized == "CPF":
        return Q(strcodigo__istartswith="cpf_")
    if normalized == "SERVIDOR":
        return Q(strcodigo__istartswith="nome_servidor_")
    if normalized == "ORGANOGRAMA":
        return (
            Q(strcodigo__icontains="orgao")
            | Q(strcodigo__icontains="unidade")
            | Q(strcodigo__icontains="organograma")
        )
    if normalized == "ARQUIVO":
        return (
            Q(strcodigo__icontains="arquivo")
            | Q(strcodigo__icontains="planilha")
            | Q(strcodigo__icontains="cabecalho")
        )
    categorized = (
        validation_subject_query("CARGO")
        | validation_subject_query("CPF")
        | validation_subject_query("SERVIDOR")
        | validation_subject_query("ORGANOGRAMA")
        | validation_subject_query("ARQUIVO")
    )
    return ~categorized
