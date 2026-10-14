"""Exceções específicas da aplicação de carga de organograma e lotação."""

from rest_framework import status
from rest_framework.exceptions import APIException


class SpreadsheetImportValidationError(APIException):
    """Mantém tipos JSON do relatório de validação da planilha."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "planilha_invalida"
    default_detail = "A planilha contém erros que impedem a importação."

    def __init__(self, report: dict):
        self.structured_errors = {"arquivo": report}
        super().__init__(self.default_detail, self.default_code)


class OrganogramSheetSelectionRequired(APIException):
    """Informa ao frontend que o upload precisa ser repetido com uma aba."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "selecao_aba_obrigatoria"
    default_detail = "Selecione a aba do organograma que deve ser importada."

    def __init__(self, report: dict):
        self.structured_errors = {"arquivo": report}
        super().__init__(self.default_detail, self.default_code)
