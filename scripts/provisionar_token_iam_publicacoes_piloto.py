"""Provisiona uma vez a credencial local M2M sem revelar seu valor."""

from config.settings.segredo_iam_publicacoes_piloto import provisionar_token


def main():
    """Não ativa processos nem modifica o .env compartilhado."""
    criado = provisionar_token()
    estado = "criado" if criado else "já existente e validado"
    print(f"Token IAM de Publicações {estado}; valor não exibido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
