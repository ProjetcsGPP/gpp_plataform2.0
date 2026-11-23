"""Identidade auditável validada pelo IAM, sem consulta ao usuário local."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IdentidadeIAM:
    """Principal mínimo para as views de Carga durante o piloto HTTP remoto."""

    id: int
    nome: str

    def __post_init__(self):
        if not isinstance(self.id, int) or isinstance(self.id, bool) or self.id < 1:
            raise ValueError("Identificador IAM inválido")
        if not isinstance(self.nome, str) or not self.nome.strip():
            raise ValueError("Nome IAM inválido")
        if len(self.nome) > 200 or any(
            ord(caractere) < 32 or ord(caractere) == 127
            for caractere in self.nome
        ):
            raise ValueError("Nome IAM inválido")

    @property
    def pk(self):
        return self.id

    @property
    def username(self):
        return self.nome

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_full_name(self):
        return self.nome
