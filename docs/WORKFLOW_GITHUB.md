# 🚀 Workflow de Desenvolvimento

## Branching

- main → produção
- feature/* → novas funcionalidades
- fix/* → correções
- hotfix/* → correções urgentes

## Fluxo

1. Criar branch a partir da main
2. Implementar alteração
3. Abrir Pull Request
4. CI executa:
   - Segurança
   - Testes parciais
   - Teste completo (quando aplicável)
5. Merge após aprovação

## Regra de ouro

NUNCA commitar direto na main