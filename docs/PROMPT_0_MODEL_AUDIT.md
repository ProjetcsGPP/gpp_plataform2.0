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


# PROMPT 0 — Auditoria de Modelos (PRÉ-REQUISITO)

**Data**: 2026-03-17  
**Repositório**: ProjetcsGPP/gpp_plataform2.0  
**Branch**: feature/policy-expansion-accounts

---

## 📋 APPS/ACCOUNTS/MODELS.PY — ANÁLISE COMPLETA

### Entidades Principais

#### 1. **Aplicacao** (tblaplicacao)
```
Campos de Negócio:
  - idaplicacao (PK): AutoField
  - codigointerno: CharField(50, unique=True)
  - nomeaplicacao: CharField(200)
  - base_url: URLField (nullable)
  - isshowinportal: BooleanField (default=True)
  
Relacionamentos:
  - FK em Role (aplicacao)
  - FK em UserRole (aplicacao)
  - FK em Attribute (aplicacao)
  
Observações:
  - isshowinportal controla visibilidade no portal
  - Sem campos de estado (ativo/desativado)
  - Sem ownership explícito
```

#### 2. **UserProfile** (tblusuario)
```
Campos de Identidade:
  - user (PK, OneToOneFK): auth.User
  - name: CharField(200)
  - orgao: CharField(100, nullable) ← CAMPO CRÍTICO IDOR
  
Campos de Referência:
  - status_usuario (FK): StatusUsuario (default=1)
  - tipo_usuario (FK): TipoUsuario (default=1)
  - classificacao_usuario (FK): ClassificacaoUsuario (default=1)
  
Campos de Auditoria:
  - idusuariocriacao (FK, nullable): User
  - idusuarioalteracao (FK, nullable): User
  - datacriacao: DateTimeField (auto_now_add=True)
  - data_alteracao: DateTimeField (auto_now=True)
  
Observações:
  - orgao é o campo de ESCOPO para IDOR (crítico em carga_org_lot)
  - Sem campo de status "ativo/inativo" direto (via StatusUsuario)
  - ClassificacaoUsuario.pode_editar_usuario é lido pelas policies
```

#### 3. **Role** (accounts_role)
```
Campos Principais:
  - idpk: AutoField (não documentado explicitamente)
  - aplicacao (FK): Aplicacao (nullable)
  - codigoperfil: CharField(100) ← IDENTIFICADOR LÓGICO
  - nomeperfil: CharField(100)
  - group (FK): auth.Group (nullable) ← Vinculado ao Django Groups
  
Constraints:
  - UniqueConstraint(aplicacao, codigoperfil)
  
Valores Especiais:
  - codigoperfil="PORTAL_ADMIN" existe e é RAIZ (proteção necessária)
  
Observações:
  - Role é sempre por aplicação
  - Group (auth.Group) é opcional mas criado automaticamente via signal
  - Sem campo de "ativo/desativado"
```

#### 4. **UserRole** (accounts_userrole)
```
Campos:
  - idpk: AutoField (não documentado explicitamente)
  - user (FK): auth.User (on_delete=CASCADE)
  - aplicacao (FK): Aplicacao (nullable, on_delete=CASCADE)
  - role (FK): Role (on_delete=CASCADE)
  
Constraints:
  - UniqueConstraint(user, aplicacao) ← 1 role por user/app
  
Observações:
  - Sem data de atribuição/expiração
  - Sem campo de "ativo/desativado"
  - Relação 1:1 por aplicação (uma role por user/app)
```

#### 5. **ClassificacaoUsuario** (tblclassificacaousuario)
```
Campos de Permissão:
  - idclassificacaousuario (PK): SmallIntegerField
  - strdescricao: CharField(100)
  - pode_criar_usuario: BooleanField (default=False)
  - pode_editar_usuario: BooleanField (default=False)
  
Observações:
  - APENAS 2 campos de permissão identificados
  - Nenhum campo específico para ações, indicadores, etc.
  - Lido diretamente pelas policies (nunca por role)
```

#### 6. **Attribute** (accounts_attribute) - ABAC
```
Campos:
  - idpk: AutoField
  - user (FK): auth.User (on_delete=CASCADE)
  - aplicacao (FK): Aplicacao (on_delete=SET_NULL, nullable)
  - key: CharField(100)
  - value: CharField(255)
  
Constraints:
  - UniqueConstraint(user, aplicacao, key)
  
Observações:
  - Simples par chave-valor
  - Pode não ter aplicacao (aplicacao nullable)
  - Sem histórico/versionamento
```

#### 7. **AccountsSession** (accounts_session) - Anti-Replay
```
Campos:
  - idpk: AutoField
  - user (FK): auth.User (on_delete=CASCADE)
  - jti: CharField(255, unique=True, indexed)
  - created_at: DateTimeField (auto_now_add=True)
  - expires_at: DateTimeField (obrigatório)
  - revoked: BooleanField (default=False, indexed)
  - revoked_at: DateTimeField (nullable)
  - ip_address: GenericIPAddressField (nullable)
  - user_agent: TextField (blank=True)
  
Índices:
  - idx(jti, revoked)
  - idx(user, revoked)
  
Observações:
  - STATELESS: session não carrega roles/permissões
  - Revogação explícita por JTI
  - Sem relacionamento com Role ou App
```

#### 8. **StatusUsuario, TipoUsuario** (auxiliares)
```
StatusUsuario (tblstatususuario):
  - idstatususuario (PK): SmallIntegerField
  - strdescricao: CharField(100)
  
TipoUsuario (tbltipousuario):
  - idtipousuario (PK): SmallIntegerField
  - strdescricao: CharField(100)
  
Observações:
  - Tabelas de referência simples
  - Sem negócio complexo
```

---

## 📋 APPS/ACOES_PNGI/MODELS.PY — ANÁLISE COMPLETA

### Entidades Principais

#### 1. **Acoes** (tblacoes) - ENTIDADE PRINCIPAL
```
Campos de Negócio:
  - idacao (PK): AutoField
  - strapelido: CharField(50)
  - strdescricaoacao: CharField(350)
  - strdescricaoentrega: CharField(100)
  - datdataentrega: DateTimeField (nullable)
  
Relacionamentos:
  - idvigenciapngi (FK, obrigatório): VigenciaPNGI
  - idtipoentravealerta (FK, nullable): TipoEntraveAlerta
  
Herança:
  - AuditableModel (traz created_by, updated_by, created_at, updated_at)
  
CRITICIDADE: Não há campos de STATUS/SITUACAO explícitos em Acoes!
  ❌ Falta: status (RASCUNHO, PENDENTE_APROVACAO, APROVADA, FINALIZADA)
  ❌ Falta: owner/criado_por
  ❌ Falta: responsavel
  
Observações:
  - Sem estado explícito (impede bloqueio de edição por estado)
  - Sem owner direto (relacionamento indireto via UsuarioResponsavel)
  - Depende de VigenciaPNGI (período/ciclo)
```

#### 2. **VigenciaPNGI** (tblvigenciapngi)
```
Campos:
  - idvigenciapngi (PK): AutoField
  - strdescricao: CharField(200)
  - datiniciovigencia: DateField
  - datfinalvigencia: DateField (nullable)
  
Herança:
  - AuditableModel
  
Observações:
  - Define período de vigência das ações
  - Sem estado (ativo/inativo)
```

#### 3. **UsuarioResponsavel** (tblusuarioresponsavel)
```
Campos:
  - idusuario (PK, OneToOneFK): auth.User
  - strtelefone: CharField(20)
  - strorgao: CharField(50) ← ESCOPO DE ÓRGÃO
  
Observações:
  - Ligação 1:1 com User
  - Não é herança de UserProfile
  - Campo strorgao duplica orgao do UserProfile
```

#### 4. **RelacaoAcaoUsuarioResponsavel** (tblrelacaoacaousuarioresponsavel)
```
Campos:
  - idacao (FK): Acoes
  - idusuarioresponsavel (FK): UsuarioResponsavel
  
Constraints:
  - unique_together = (idacao, idusuarioresponsavel)
  
Observações:
  - M:N entre Acao e UsuarioResponsavel
  - Define who is responsible for an action
```

#### 5. **Entidades Secundárias**

##### AcaoPrazo (tblacaoprazo)
```
Campos:
  - idacaoprazo (PK): AutoField
  - idacao (FK): Acoes
  - isacaoprazoativo: BooleanField (default=True)
  - strprazo: CharField(50)

Observações:
  - Prazo associado à ação
  - Pode estar ativo/inativo
  - Sem data de vencimento explícita
```

##### AcaoDestaque (tblacaodestaque)
```
Campos:
  - idacaodestaque (PK): AutoField
  - idacao (FK): Acoes
  - datdatadestaque: DateTimeField

Observações:
  - Apenas marca uma ação como destaque em uma data
```

##### AcaoAnotacaoAlinhamento (tblacaoanotacaoalinhamento)
```
Campos:
  - idacaoanotacaoalinhamento (PK): AutoField
  - idacao (FK): Acoes
  - idtipoanotacaoalinhamento (FK): TipoAnotacaoAlinhamento
  - strdescricao: TextField

Observações:
  - Anotação/comentário tipificado
  - Associado à ação
```

#### 6. **Entidades de Referência**

##### Eixo (tbleixos)
```
Campos:
  - ideixo (PK): AutoField
  - strdescricaoeixo: CharField(100)
  - stralias: CharField(5, unique=True)

Herança: AuditableModel

Observações:
  - Eixo temático (ex: Educação, Saúde)
  - Não relacionado a Acoes no models (possível falta?)
```

##### SituacaoAcao (tblsituacaoacao)
```
Campos:
  - idsituacaoacao (PK): AutoField
  - strdescricaosituacao: CharField(50, unique=True)

Observações:
  - Tabela de referência
  - Não ligada a Acoes! ❌ POSSÍVEL BUG DE DESIGN
```

---

## 📋 APPS/CARGA_ORG_LOT/MODELS.PY — ANÁLISE COMPLETA

### Entidades Principais

#### 1. **TokenEnvioCarga** (tbltokenenviocarga) - ENTIDADE PRINCIPAL
```
Campos:
  - idtokenenviocarga (PK): BigAutoField
  - strtoken: CharField(200)
  - idtipocarga (FK, obrigatório): TipoCarga
  - idstatusprogresso (FK, obrigatório): StatusProgresso
  
Herança:
  - AuditableModel
  
CRITICIDADE: Nenhum campo de "orgao" ou escopo IDOR direto!
  ❌ Falta: orgao (vinculação a órgão do usuário)
  ❌ Falta: created_by (quem enviou)
  
Observações:
  - Representa um envio de carga (token)
  - Status via StatusProgresso
  - Sem escopo de órgão explícito → IDOR crítico!
```

#### 2. **Patriarca** (tblpatriarca)
```
Campos:
  - idpatriarca (PK): BigAutoField
  - idexternopatriarca: UUIDField (unique=True)
  - strsiglapatriarca: CharField(20)
  - strnome: CharField(255)
  - datcriacao: DateTimeField
  - datalteracao: DateTimeField (nullable)
  - idstatusprogresso (FK): StatusProgresso
  
Herança:
  - AuditableModel
  
Observações:
  - Representa uma entidade patriarca (órgão pai?)
  - Sem campo de "orgao" explícito
  - Status via StatusProgresso
```

#### 3. **DetalheStatusCarga** (tbldetalhestatuscarga)
```
Campos:
  - iddetalhestatuscarga (PK): BigAutoField
  - idtokenenviocarga (FK): TokenEnvioCarga
  - idstatuscarga (FK): StatusCarga
  - strmensagem: TextField
  
Herança:
  - AuditableModel
  
Observações:
  - Log/histórico de status de uma carga
  - Detalha cada mudança de estado
```

#### 4. **Entidades de Referência**

##### StatusCarga (tblstatuscarga)
```
Campos:
  - idstatuscarga (PK): SmallIntegerField
  - strdescricao: CharField(150)
  - flgsucesso: IntegerField
  
Observações:
  - Estados: PENDENTE, PROCESSANDO, CONCLUIDO, ERRO, CANCELADO (inferido)
  - flgsucesso indica sucesso/falha
```

##### StatusProgresso (tblstatusprogresso)
```
Campos:
  - idstatusprogresso (PK): SmallIntegerField
  - strdescricao: CharField(100)
  
Observações:
  - Estados genéricos de progresso
```

##### TipoCarga (tbltipocarga)
```
Campos:
  - idtipocarga (PK): SmallIntegerField
  - strdescricao: CharField(100)
  
Observações:
  - Tipos de carga (ex: Usuários, Órgãos, etc.)
```

---

## 🚨 PROBLEMAS E LACUNAS IDENTIFICADAS

### Em apps/accounts:
1. ✅ **Bem definido**: UserProfile, Role, UserRole, AccountsSession
2. ⚠️ **Incompleto**: Sem status "ativo/inativo" em Role, UserRole
3. ✅ **IDOR protegido**: UserProfile.orgao é o escopo

### Em apps/acoes_pngi:
1. ❌ **CRÍTICO**: Acoes não tem campo `status`
   - Impede bloqueio de edição por estado
   - SituacaoAcao existe mas não está FK em Acoes
2. ❌ **CRÍTICO**: Acoes não tem `owner` direto
   - Vinculação só via RelacaoAcaoUsuarioResponsavel (M:N)
3. ⚠️ **Falta**: Sem relacionamento entre Eixo e Acoes
4. ⚠️ **Falta**: Sem campos de aprovação/workflow

### Em apps/carga_org_lot:
1. ❌ **CRÍTICO**: TokenEnvioCarga não tem `orgao`
   - IDOR total: qualquer user pode ver cargas de qualquer órgão
   - Deve vincular a UserProfile.orgao do usuario criador
2. ❌ **CRÍTICO**: TokenEnvioCarga não tem `created_by`
   - Impossível auditar quem criou a carga
3. ⚠️ **Falta**: Sem estado/ciclo de vida explícito
4. ⚠️ **Falta**: Sem relacionamento com Patriarca/Órgão de forma clara

---

## 📌 RECOMENDAÇÕES PRÉ-PROMPT 1

### Ações Necessárias ANTES de Implementar Policies:

1. **Em apps/acoes_pngi/models.py**:
   ```python
   # ADICIONAR a Acoes:
   status = models.CharField(
       max_length=50,
       choices=[
           ('RASCUNHO', 'Rascunho'),
           ('PENDENTE_APROVACAO', 'Pendente de Aprovação'),
           ('APROVADA', 'Aprovada'),
           ('FINALIZADA', 'Finalizada'),
       ],
       default='RASCUNHO'
   )
   criado_por = models.ForeignKey(
       settings.AUTH_USER_MODEL,
       on_delete=models.SET_NULL,
       null=True,
       related_name="acoes_criadas"
   )
   
   # ADICIONAR FK em Acoes:
   # ideixo = models.ForeignKey(Eixo, on_delete=models.PROTECT)
   # idsituacaoacao = models.ForeignKey(SituacaoAcao, on_delete=models.PROTECT)
   ```

2. **Em apps/carga_org_lot/models.py**:
   ```python
   # ADICIONAR a TokenEnvioCarga:
   orgao = models.CharField(max_length=100)  # Escopo IDOR
   criado_por = models.ForeignKey(
       settings.AUTH_USER_MODEL,
       on_delete=models.SET_NULL,
       null=True,
       related_name="cargas_criadas"
   )
   
   # CONSTRAINT:
   # Validar em save() que criado_por.profile.orgao == self.orgao
   ```

3. **Migração de Dados**:
   - Criar migrations para adicionar os campos acima
   - Preencher dados históricos com valores padrão
   - Testar integridade referencial

---

## ✅ CONCLUSÃO

**Status**: Auditoria COMPLETA
**Data**: 2026-03-17

Os modelos têm estrutura básica sólida mas apresentam **3 lacunas críticas**:
1. Falta de status em Acoes (bloqueia políticas de workflow)
2. Falta de owner em Acoes (impede validação de propriedade)
3. **IDOR crítico** em TokenEnvioCarga (sem escopo de orgao)

**Recomendação**: Aguardar correção dos pontos acima antes de prosseguir com Prompts 1-3.