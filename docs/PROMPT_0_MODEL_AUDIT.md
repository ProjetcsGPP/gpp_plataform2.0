# Auditoria do Modelo

## Modelos Abrangidos

- `apps/accounts`
- `apps/acoes_pngi`
- `apps/carga_org_lot`

### 1. apps/accounts

O modelo `accounts` gerencia todas as contas de usuário, permitindo operações como criação, leitura, atualização e exclusão (CRUD). É essencial para a autenticação e autorização dentro do sistema. Os principais campos incluem:

- **account_id**: Identificador único da conta.
- **user_id**: Referência ao usuário associado.
- **created_at**: Timestamp da criação.
- **updated_at**: Timestamp da última atualização.

### 2. apps/acoes_pngi

O modelo `acoes_pngi` lida com ações relacionadas ao PINGI (Programa de Incentivo a Novos Investimentos). Este modelo ajuda a rastrear as ações tomadas pelos usuários e suas respectivas consequências. Campos importantes incluem:

- **acao_id**: Identificador único para a ação.
- **descricao**: Descrição da ação realizada.
- **user_id**: Referência ao usuário que executou a ação.
- **created_at**: Timestamp da criação da ação.

### 3. apps/carga_org_lot

O modelo `carga_org_lot` é responsável pela carga de dados organizados em lotes. Este modelo é utilizado para importar grandes volumes de dados de forma eficiente. Os principais campos são:

- **lot_id**: Identificador do lote.
- **data_inicial**: Data de início do lote de carga.
- **data_final**: Data de conclusão do lote de carga.
- **status**: Status do lote (em andamento, concluído, falhado).

### Considerações Finais

A auditoria dos modelos acima garante a integridade e eficiência das operações. É fundamental manter a documentação atualizada para facilitar a manutenção e evolução do sistema.