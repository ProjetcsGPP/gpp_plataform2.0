# E1 — Inventário de acesso entre aplicações

**Levantamento:** 2026-11-26, branch `feat/backend-isolamento-aplicacoes`.
**Escopo:** interações operacionais entre domínios, composição Django, modelos
carregados e migrações relevantes. Rotinas de implantação não integram este
inventário operacional. É um inventário do checkout, não prova de comportamento
de todo o banco ou da implantação. Não houve alteração de dados ou serviços.

## Resultado

| Fluxo | Leitura/escrita constatada | Classificação e encaminhamento |
| --- | --- | --- |
| E-Docs → Publicações: patriarcas | `services/patriarcas_edocs.py` lê a API E-Docs e cria uma coleta, uma observação por registro remoto, divergências quando necessário e auditoria, tudo em `pub_institucional`. A coleta **não** grava `PatriarcaEdocs`; inclusão, atualização ou desativação só ocorre na função de decisão humana. | **Não é acesso entre apps.** O catálogo E-Docs pertence a Publicações. Carga possui outro cadastro `Patriarca`, sem vínculo ORM. Eventual compartilhamento de registros confirmados permanece em aberto, fora deste incremento. |
| Publicações → IAM: autorização local legada | `permissoes_iam.py` importa `AuthorizationService` de `accounts` no modo não piloto; no piloto usa `common.services.cliente_iam` para decisão interna. | Leitura/decisão cruzada, **não** escrita. Manter legado até corte; não ampliar import direto. |
| Carga/Ações → `core` → IAM | Carga e Ações importam `core.permissions`; Carga WebSocket ainda tem caminho local em `core.services.autorizacao_iam_local`. | Dependência de autorização existente. Carga tem piloto remoto opt-in; Ações ainda precisa de contrato/perfil próprio. |
| Portal autenticado → IAM | `portal/views.py` e `serializers.py` consultam `Aplicacao` e `UserRole` de `accounts`. | Leitura direta dentro da composição atual IAM/Portal. Se Portal se tornar processo próprio, substituir por DTO IAM. A API pública de Publicações não segue esse caminho. |
| `common` e `config` | `common/permissions.py` reexporta `core.permissions`; `common/admin_site.py` conhece nomes de modelos IAM; `config` monta apps/rotas/filas. | Acoplamento de apresentação/compatibilidade e composição, não escrita entre domínios. Rever no empacotamento; `common` não deve virar serviço de regras de negócio. |

## Dados e caminhos indiretos

As entidades IAM são mantidas atualmente pelo Django Admin. As APIs de
usuários e vínculos de perfil já oferecem operações administrativas; as de
aplicações, capabilities e menus não formam ainda uma gestão completa por
páginas. A direção funcional é oferecer primeiro essas páginas no Portal,
com escopo global para seu gestor, e depois nas aplicações, com escopo
restrito à própria aplicação para seus gestores. O serviço IAM deverá impor
esse escopo por ação e objeto; a interface não será a fronteira de segurança.
Essa evolução não altera a propriedade do cadastro de patriarcas de Carga.

**Rechecagem da `main` (`856b669`, 26/11/2026):**
`sincronizar_patriarcas_edocs()` chama a API E-Docs, normaliza e passa o
resultado a `_persistir_comparacao()`. Esta cria `ObservacaoPatriarcaEdocs`
para cada registro, `DivergenciaPatriarcaEdocs` para novos/alterados/ausentes,
atualiza o resumo de `ColetaPatriarcasEdocs` e registra auditoria. Somente
`aplicar_decisao_divergencia_patriarca()` faz `PatriarcaEdocs.objects.create`
ou altera/desativa um `PatriarcaEdocs`, após decisão válida e justificativa.
As observações já contêm os campos normalizados necessários à comparação; a
divergência mantém o retrato observado para aplicar a decisão. Não há motivo
para criar outro JSON de patriarcas no IAM.

- Os modelos carregados são 25 de Carga no schema `carga_org_lot`, 27 de
  Publicações em `publicacoes` e 10 de Ações em `acoes_pngi`. A introspecção
  de campos concretos não encontrou FK/M2M ativa entre essas três apps.
- `common.models.AuditableModel` guarda IDs/nome do ator como dados lógicos,
  sem FK para `auth_user`. Ações também guarda ID lógico de responsável.
- Migrações antigas de Carga e Ações referenciam `AUTH_USER_MODEL`;
  Publicações removeu a FK de preferência E-Flow na 0015. O estado final dos
  modelos não substitui uma revisão do histórico antes de migrar isoladamente.
- A busca por `apps.get_model`, ORM de IAM, SQL explícito e imports de produção
  não encontrou outra escrita cruzada nas apps de negócio. O SQL direto
  localizado em Publicações é o bloqueio consultivo PostgreSQL da coleta
  E-Docs, sem acesso a tabela de outra app.
- `config/settings/base.py` registra todas as apps e agenda tarefas de Carga e
  Publicações; perfis opt-in têm rotas/filas próprias. Isso é acoplamento de
  composição operacional, não acesso a dados de outra app.

## Limites e controle

**Retomada de 26/11/2026:** as quatro verificações de
`apps/core/tests/test_fronteiras_dominio.py` passaram tanto na execução
direta sem banco quanto no `pytest -q --no-cov --tb=line` com o banco
permanente `test_gpp_plataform` (4 aprovados). A primeira tentativa do
`pytest` no executor restrito não alcançou as asserções por falta de conexão
ao PostgreSQL; a repetição com acesso ao banco resolveu a limitação.
`manage.py check` também passou. A inspeção de URLs confirmou perfis piloto
distintos para IAM/Portal, Carga e Publicações;
o perfil IAM separado ainda serve Ações PNGI. A busca de acessos dinâmicos
e SQL de produção encontrou somente o bloqueio consultivo da coleta E-Docs
fora de migrações; não foi detectado acesso dinâmico entre apps de negócio.

Esta varredura não prova ausência de SQL montado dinamicamente, importação
por string fora das buscas, acesso feito por dependência externa nem de
restrições físicas legadas no PostgreSQL. A revisão do catálogo e dos grants
do banco continua no gate final de dados, conforme decisão do responsável.

`apps/core/tests/test_fronteiras_dominio.py` impede novos imports literais
entre domínios, FK/M2M ativas entre eles e novos imports literais de
`accounts` em apps de negócio. O teste congela somente duas exceções legadas
de Publicações (`permissoes_iam.py` e `recursos_funcionais.py`); não as aprova
como arquitetura definitiva. Também impede `core`/`common` de importar apps
de negócio. Não altera os perfis ou a autorização em operação.
