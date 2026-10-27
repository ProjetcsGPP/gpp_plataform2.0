# Guia operacional do OpenBao em DEV

**Escopo:** estação de desenvolvimento deste projeto  
**Não define:** operação, rotação ou arquitetura de HML/PRD

## 1. Para que ele existe aqui

O OpenBao guarda credenciais técnicas que não devem permanecer no `.env`, no
banco funcional, no Git ou em logs. Hoje o uso real é a credencial
`client_credentials` do CargaRH/PRODEST.

Ele não guarda publicações, planilhas, usuários nem dados do portal. A perda do
OpenBao pode interromper uma integração, mas não apaga os dados funcionais do
PostgreSQL.

Em DEV ele roda em um único container, acessível somente por
`127.0.0.1:58200`, e persiste dados em um volume Docker. Não é necessário
instalar a CLI `bao` no host; os scripts chamam a CLI dentro do container.

### Ele é obrigatório em todo desenvolvimento?

Não. Para trabalho que não chama a integração CargaRH, o OpenBao pode ficar
parado. Em uma estação individual, um `.env` ignorado pelo Git e protegido pelo
sistema operacional é uma alternativa mais simples para segredos exclusivamente
locais.

O valor do OpenBao neste projeto é exercitar a interface de cofre, separar HML
de PRD e impedir que uma credencial externa já existente permaneça misturada às
demais variáveis. A recomendação proporcional é mantê-lo sob demanda para os
testes de integração que precisam desse contrato, sem transformá-lo em
dependência de todo comando Django nem em requisito automático para outros
desenvolvedores. A decisão de mantê-lo ou retornar a um provedor `.env` em DEV
pode ser revista sem alterar o contrato do `CargaRHClient`.

## 2. Como a aplicação o utiliza

```text
CargaRHClient
    -> resolvedor de credenciais HML ou PRD
       -> login AppRole com RoleID + SecretID
          -> token temporário e limitado
             -> leitura do caminho KV v2 permitido
```

- `RoleID`: identifica a identidade da aplicação;
- `SecretID`: comprova que ela pode usar essa identidade;
- policy: limita exatamente o que essa identidade pode ler;
- token: sessão temporária emitida depois do login;
- KV v2: armazenamento versionado dos pares `client_id` e `client_secret`.

HML e PRD usam AppRoles e caminhos diferentes. Uma não pode ler a outra e
nenhuma delas pode escrever. O usuário não precisa fazer login no OpenBao para
usar normalmente o CargaRH: o backend executa esse fluxo automaticamente.

## 3. Operação normal

### Iniciar ou recuperar após reinício

```bash
infra/publicacoes-dev/scripts/bootstrap-openbao.sh
```

Esse comando inicia o container, inicializa somente um cofre novo, desbloqueia
quando necessário e garante engines, policies e AppRoles. O bootstrap normal
preserva os `SecretID` e as credenciais existentes.

### Ver se o container está ativo

```bash
infra/publicacoes-dev/scripts/compose.sh ps openbao
```

### Validar o contrato sem mostrar segredos

```bash
infra/publicacoes-dev/scripts/preflight.sh
```

O preflight verifica leitura permitida, leitura proibida entre HML/PRD e
negação de escrita. Ele não imprime `client_id`, `client_secret`, `SecretID` ou
token.

### Parar sem apagar dados

```bash
infra/publicacoes-dev/scripts/compose.sh stop openbao
```

O volume, as chaves locais e os segredos permanecem preservados.

## 4. Cadastrar uma credencial

Antes de cadastrar, diferencie os dois grupos de valores:

| Valor | Onde configurar |
|---|---|
| URL base da API, URL do token, escopo e ambiente-alvo | `.env` ou variáveis do processo |
| `client_id` e `client_secret` | OpenBao |

As URLs confirmadas para a API são:

```env
CARGARH_HML_API_BASE_URL=https://api.cargarh.hom.es.gov.br/
CARGARH_PRD_API_BASE_URL=https://api.cargarh.es.gov.br/
CARGARH_HML_CLIENT_SCOPE="api-cargarh-base api-cargarh-inicial"
CARGARH_PRD_CLIENT_SCOPE="api-cargarh-base api-cargarh-inicial"
```

Elas não devem ser cadastradas no OpenBao porque não são segredos. Depois de
alterar uma variável do processo, reinicie Django e Celery para recarregar os
settings. Os escopos têm hoje o mesmo valor, mas permanecem separados para que
uma eventual alteração da PRODEST em um ambiente não afete o outro.

Para HML:

```bash
.venv/bin/python \
  infra/publicacoes-dev/scripts/provision_cargarh_secret.py \
  --environment HML
```

Para PRD, trocar `HML` por `PRD`. O programa solicita `client_id` e
`client_secret`; o segredo é digitado sem eco no terminal. Executar novamente
substitui deliberadamente o valor daquele ambiente, portanto não deve ser usado
como rotina periódica.

## 5. Política de substituição em DEV

DEV não possui calendário de rotação. Uma credencial ou identidade somente é
substituída quando houver ação explícita, perda, expiração já ocorrida ou
incidente concreto. Rotação programada e processo sem indisponibilidade serão
definidos para HML/PRD no momento apropriado.

Se um `SecretID` local estiver ausente ou comprovadamente inválido:

```bash
infra/publicacoes-dev/scripts/bootstrap-openbao.sh \
  --replace-app-identities
```

Essa opção substitui somente identidades AppRole locais. Ela não altera a
credencial emitida pela PRODEST.

## 6. O que existe em `runtime/openbao`

| Arquivo | Finalidade | Sensibilidade |
|---|---|---|
| `init.json` | chave de desbloqueio e token administrativo local | crítica |
| `role_id` / `secret_id` | identidade do preflight de `PUBLICACOES` | restrita |
| `carga_org_lot_*_role_id` | identidade de leitura HML ou PRD | restrita |
| `carga_org_lot_*_secret_id` | prova secreta da identidade | crítica |
| `status.json` | último estado técnico consultado | operacional |

O diretório é ignorado pelo Git e os arquivos sensíveis usam modo 0600. Nunca
copiar seu conteúdo para issue, chat, documentação ou log.

## 7. Recuperação após perda

| Situação | Consequência | Ação em DEV |
|---|---|---|
| Container parado | aplicação não lê novos segredos | executar o bootstrap normal |
| Cofre selado após reinício | leituras ficam indisponíveis | bootstrap usa `init.json` para desbloquear |
| Arquivo AppRole perdido/inválido | somente aquela identidade não autentica | usar `--replace-app-identities` |
| Volume perdido, mas credencial externa conhecida | dados do cofre são perdidos | recriar o cofre e cadastrar novamente a credencial |
| `init.json` perdido e cofre posteriormente selado | conteúdo existente fica irrecuperável | restaurar cópia protegida ou recriar e reprovisionar |
| Volume e `init.json` perdidos | cofre local perdido | recriar; dados Django não são afetados |
| Credencial PRODEST também desconhecida | integração não pode ser recomposta | solicitar nova emissão à PRODEST |

Apagar volume, reinicializar o cofre ou restaurar snapshot são operações
destrutivas e exigem decisão explícita. Não há job periódico de backup do
OpenBao em DEV. Se a credencial não puder ser reemitida facilmente, deve-se
aprovar antes uma cópia protegida de `init.json` e um snapshot Raft, armazenados
separadamente; isso não será criado por suposição.

## 8. Diagnóstico rápido

1. executar `compose.sh ps openbao`;
2. executar o bootstrap normal;
3. executar o preflight;
4. conferir se `CARGARH_ENVIRONMENT` seleciona `HML` ou `PRD`;
5. se apenas a identidade falhar, usar a substituição explícita;
6. se o segredo estiver ausente, provisioná-lo novamente;
7. nunca imprimir arquivos, tokens ou respostas completas para investigar.

## 9. Limites desta configuração

- HTTP sem TLS é aceito somente no loopback de DEV;
- há um único nó, sem alta disponibilidade;
- `init.json` reúne a única chave de desbloqueio e o token administrativo;
- não existe backup automático;
- AppRole em arquivo é uma solução local, não uma decisão de HML/PRD;
- ambientes futuros deverão definir identidade, TLS, backup e recuperação.

## 10. Referências oficiais

- [Inicialização e chaves de desbloqueio](https://openbao.org/docs/commands/operator/init/)
- [Autenticação AppRole](https://openbao.org/docs/auth/approle/)
- [Armazenamento integrado Raft](https://openbao.org/docs/configuration/storage/raft/)
- [Snapshots Raft](https://openbao.org/docs/commands/operator/raft/)
