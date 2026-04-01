# 🧪 Estratégia de Testes

## Cobertura

- Cobertura global validada via suíte completa (`pytest`)
- Meta mínima: 80%
- Atual: ~93%

## Tipos de testes

### 🔐 Auth
- Arquivo: test_multi_cookie.py
- Escopo: middleware e autenticação

### 🔑 Policies
- Diretório: tests/policies/
- Escopo: regras RBAC

### 🌐 Full
- Executa toda a suíte
- Único responsável por validar cobertura global

## Observação importante

Testes parciais (auth/policies) NÃO representam cobertura total do sistema.
A cobertura oficial é validada apenas no job FULL.