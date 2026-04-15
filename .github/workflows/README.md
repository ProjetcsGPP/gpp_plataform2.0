# 🚀 Security & Quality Pipeline

Este diretório contém o workflow de CI/CD responsável por garantir **segurança, qualidade e confiabilidade** do projeto.

---

# 🧩 Visão Geral

O pipeline executa automaticamente em:

* `push` na branch `main`
* `pull_request`

Ele é dividido em dois grandes blocos:

1. 🔐 Segurança
2. 🧪 Testes + Qualidade de Código

---

# 🔐 Segurança (Security Scan)

Executado com estratégia em paralelo (matrix).

## Ferramentas utilizadas

### 🔍 CodeQL

Análise estática de segurança (SAST).

Detecta:

* injection (SQL, command, etc.)
* falhas de autenticação/autorização
* uso inseguro de cookies
* problemas de fluxo de dados

---

### 🔑 Gitleaks

Detecta vazamento de segredos.

Exemplos:

* tokens
* passwords
* chaves de API

---

### 📦 Trivy

Análise de vulnerabilidades em dependências (SCA).

Detecta:

* CVEs em bibliotecas Python
* vulnerabilidades conhecidas no ambiente

---

# 🧪 Testes e Qualidade

Executado com banco PostgreSQL isolado para garantir consistência.

---

## 🔍 Code Quality (antes dos testes)

### Flake8

* Verificação de estilo e erros simples
* Falha o build em problemas relevantes

---

### Pylint

* Análise de code smells
* Detecta:

  * funções complexas
  * má organização
  * duplicação
  * problemas de design

**Regra atual:**

```
pylint apps --fail-under=7.5
```

---

### Radon

* Mede complexidade ciclomática
* Avalia manutenibilidade

**Modo atual:**

* Apenas reporta (não bloqueia o build)

---

## 🧪 Testes

Executa a suíte completa:

```
pytest --cov=apps --cov=common --cov-report=term-missing --cov-fail-under=80
```

### Cobertura mínima:

* **80% (obrigatório)**

---

# 🧠 Estratégia do Pipeline

Ordem de execução:

1. Segurança (paralelo)
2. Qualidade de código
3. Testes

Isso garante:

* código inseguro é identificado cedo
* code smells são detectados antes dos testes
* apenas código de qualidade segue para validação completa

---

# 📈 Possíveis Melhorias Futuras

## 🔥 Aumentar rigor do Pylint

Atual:

```
--fail-under=7.5
```

Futuro:

```
--fail-under=8.5
```

---

## 🔥 Tornar Radon bloqueante

Atual:

```
radon cc apps -nc -s
```

Futuro:

```
radon cc apps -nb --fail-under B
```

---

## 🔥 Executar pipeline também em Pull Requests

Atual:

```
if: github.event_name == 'push'
```

Melhoria:

```
if: github.event_name == 'push' || github.event_name == 'pull_request'
```

---

## 🔥 Paralelismo com pytest-xdist

Melhoria de performance:

```
pytest -n auto
```

---

## 🔥 Badge de qualidade e cobertura

Adicionar ao README principal:

* coverage badge
* qualidade do código
* status do pipeline

---

## 🔥 Configuração dedicada de lint

Criar arquivos:

### `.pylintrc`

* regras customizadas para Django
* ajuste de falsos positivos

### `.flake8`

* padronização de estilo
* definição de limites (linha, imports, etc.)

---

## 🔥 Integração com análise contínua

Possíveis ferramentas:

* SonarQube
* CodeFactor

---

# ⚠️ Boas Práticas

* Não ignorar alertas de segurança sem justificativa
* Sempre documentar dismiss de CodeQL
* Validar inputs críticos (ex: autenticação, cookies)
* Manter coverage ≥ 80%
* Evitar crescimento de complexidade (Radon)
* Revisar warnings de Pylint regularmente

---

# 🧾 Observações

* O pipeline está preparado para ambiente de produção
* Segue boas práticas modernas de segurança e qualidade
* Pode ser evoluído gradualmente conforme maturidade do projeto

---

# 🚀 Conclusão

Este pipeline garante:

* 🔐 Segurança do código
* 📦 Segurança das dependências
* 🔑 Proteção contra vazamento de segredos
* 🧪 Confiabilidade via testes
* 🧠 Qualidade e manutenibilidade

---
