# Guia Operacional Futuro

**Status:** desenho da operação; telas e nomes podem mudar  
**Perfil funcional inicial:** `GESTOR_PUBLICACOES`

## 1. Atores

### Visitante público

- consulta dashboard e publicações liberadas;
- não possui conta ou role para essa finalidade;
- nunca vê rascunhos, relatórios internos ou artefatos de origem.

### Usuário autenticado do Portal

- realiza login pela modal do Portal;
- vê as aplicações às quais possui acesso;
- só entra em `PUBLICACOES` se possuir vínculo apropriado.

### Gestor de publicações

- administra fontes conforme suas permissões;
- acompanha coletas e validações;
- prepara e revisa publicações;
- publica, substitui ou revoga quando autorizado;
- administra consumidores e credenciais quando autorizado;
- consulta histórico e evidências.

### Administrador da plataforma

- cadastra a aplicação, role, capabilities, menus e vínculos de usuários;
- apoia sessão, permissões e infraestrutura;
- não se torna automaticamente responsável funcional pelo conteúdo;
- mantém o acesso administrativo global vigente nas demais aplicações;
- quando executar ação editorial, deve cumprir as mesmas transições,
  justificativas, validações e registros de auditoria do gestor.

### Consumidor de API

- é uma identidade de sistema, não usuário ou role;
- acessa somente escopos contratados;
- é responsável pela guarda e rotação de sua credencial.

## 2. Perfil inicial

Um único perfil `GESTOR_PUBLICACOES` é suficiente para a primeira versão porque
o sistema já distribui permissões técnicas de forma granular. A role representa
o agrupamento institucional; as ações são autorizadas por permissões, sem
condicionais de nome de role no frontend.

Na primeira versão, a mesma pessoa poderá preparar e publicar. O workflow não
exigirá um segundo usuário, mas verificará as permissões técnicas de cada ação e
registrará separadamente preparação, publicação, data, justificativa e autoria.

## 3. Jornada de implantação de um gestor

1. Administrador cadastra ou localiza o usuário.
2. Associa `GESTOR_PUBLICACOES` na aplicação `PUBLICACOES`.
3. O sincronizador materializa as permissões efetivas.
4. Gestor autentica na aplicação.
5. Menus aparecem conforme capabilities distribuídas.
6. Botões e endpoints respeitam permissões técnicas.
7. Toda ação sensível registra usuário, data e justificativa.

## 4. Jornada de cadastro de fonte

1. Gestor inicia cadastro em rascunho.
2. Informa proprietário, finalidade, tipo e classificação.
3. Seleciona conector previamente aprovado.
4. Equipe técnica provisiona segredo fora da tela de negócio.
5. Sistema testa autenticação e conectividade sem revelar segredo.
6. Contrato/schema é validado com amostra controlada.
7. Segurança e responsável da fonte aprovam ativação.
8. Fonte é ativada e monitorada.

Falha em teste não deve apagar a configuração nem expor resposta bruta
sensível. A ativação precisa de histórico e justificativa.

## 5. Jornada de uma publicação

1. Um snapshot válido fica disponível manualmente ou por integração.
2. Gestor cria uma publicação candidata.
3. Sistema apresenta fontes, versões, hashes e período de referência.
4. Cálculos são executados no backend e registrados.
5. Validações bloqueantes e avisos são apresentados separadamente.
6. Gestor corrige a fonte/candidato ou confirma os avisos permitidos.
7. Gestor visualiza exatamente o conteúdo público futuro.
8. Publica informando justificativa.
9. Sistema congela o snapshot, atualiza o ponteiro vigente e invalida cache.
10. API e Portal passam a servir a nova versão.

A primeira versão não exige dupla aprovação, conforme ADR-0001. Uma futura
segregação de funções dependerá de novo ADR, migração compatível e revisão da
matriz; até lá, não deve ser inferida por tela, serviço ou teste.

## 6. Correção, substituição e revogação

### Correção

- nunca editar publicação liberada;
- criar nova versão baseada na anterior;
- registrar motivo e diferenças;
- validar e publicar pelo workflow normal.

### Substituição

- nova versão torna-se vigente atomicamente;
- anterior fica `SUBSTITUIDA` e consultável historicamente;
- URLs por UUID continuam representando o snapshot original.

### Revogação

- usar para conteúdo que não deve continuar vigente;
- exigir justificativa e permissão específica;
- retirar do endpoint “vigente” e invalidar cache;
- preservar evidência e acesso administrativo;
- definir previamente a mensagem pública substituta.

## 7. Cadastro de consumidor da API

1. Gestor registra sistema, responsável, finalidade e ambiente.
2. Define recursos, escopos, quota e validade.
3. Aprovação técnica/segurança é registrada.
4. Sistema gera credencial e mostra o segredo uma única vez.
5. Segredo é entregue por canal seguro.
6. Consumidor confirma chamada de teste.
7. Uso e anomalias passam a ser monitorados.

Nunca enviar segredo por e-mail comum, ticket público, log ou comentário de PR.

## 8. Rotação e revogação de credencial

### Rotação planejada

1. gerar nova credencial;
2. manter sobreposição curta e registrada;
3. consumidor migra e comprova uso da nova;
4. revogar a antiga;
5. verificar ausência de chamadas antigas.

### Comprometimento

1. revogar imediatamente;
2. preservar logs;
3. comunicar segurança e responsável;
4. avaliar dados acessados;
5. emitir nova credencial somente após contenção;
6. registrar incidente e ações corretivas.

## 9. Rotina operacional

### Canal inicial de incidentes

Enquanto não houver equipe ou substituto formal, o desenvolvedor responsável
receberá as notificações operacionais por conta Zimbra fornecida pela PRODEST.
O e-mail é canal de aviso, não fonte de verdade. Cada mensagem deverá apontar
para um identificador persistido de incidente/evento/job; o detalhamento
canônico permanecerá nos logs estruturados e na auditoria restrita.

O backend utilizará integração aprovada com TLS e credencial em secret store.
Não dependerá de Google Apps Script em runtime, não aceitará HTTP sem
criptografia e não copiará segredos ou dados restritos para assunto/corpo. A
entrega terá deduplicação, retry limitado, rate limit e falha observável.

A configuração atual do canal é a mesma, mas será cadastrada em dois perfis
lógicos independentes para acompanhar o padrão existente do OpenBao:

| Parâmetro | HML | PRD |
|---|---|---|
| Servidor | `seger.correio.es.gov.br` | `seger.correio.es.gov.br` |
| Porta | `443` | `443` |
| Caminho SOAP | `/service/soap` | `/service/soap` |
| Remetente | `acoesgpp@seger.es.gov.br` | `acoesgpp@seger.es.gov.br` |
| Nome exibido | `Ações GPP` | `Ações GPP` |
| Caminho KV v2 | `publicacoes/dev/zimbra/hml` | `publicacoes/dev/zimbra/prd` |

Embora os dados de origem usem nomes iniciados por `SMTP_`, porta `443` e
`/service/soap` caracterizam uma integração SOAP sobre HTTPS, não uma sessão
SMTP. O backend deverá usar `ZIMBRA_ENVIRONMENT=HML|PRD` para selecionar um
perfil e configurações explícitas como `ZIMBRA_HML_SOAP_URL`,
`ZIMBRA_PRD_SOAP_URL`, `ZIMBRA_HML_OPENBAO_SECRET_PATH` e
`ZIMBRA_PRD_OPENBAO_SECRET_PATH`. O `secret path` identifica o registro KV que
contém a senha; ele não deve ser confundido com o `SecretID` usado pela AppRole
para autenticar o backend no OpenBao.

A senha não integra esta tabela. Por decisão do responsável, a credencial atual
será mantida nesta etapa apesar da exposição registrada. O aceite de risco não
permite copiá-la para documentação, Git, `.env`, log ou argumento de linha de
comando: o provisionador deverá solicitá-la sem eco no terminal e gravá-la
diretamente nos dois caminhos. Cada perfil terá AppRole e policy de leitura
próprias; atualizações posteriores serão explícitas por perfil ou
conjuntamente, nunca sincronizadas de forma implícita. A ativação exige teste
de autenticação, envio, correlação, deduplicação, retry e falha de entrega nos
dois perfis. A rotação continua recomendada, mas não bloqueia este
provisionamento por decisão registrada.

### Diária

- falhas de coleta e filas pendentes;
- publicações aguardando ação;
- fontes indisponíveis;
- credenciais com comportamento anômalo;
- alertas de segurança.

### Semanal

- dead-letter e retries recorrentes;
- divergências de reconciliação;
- crescimento de storage;
- consumidores próximos da quota;
- publicações e fontes sem responsável válido.

### Mensal

- credenciais próximas do vencimento;
- revisão de acessos e overrides;
- fontes e consumidores inativos;
- retenção e descarte;
- restauração amostral conforme política;
- atualização de dependências e vulnerabilidades.

## 10. Treinamento antes do go-live

Gestores devem praticar em homologação:

- criar, validar e publicar conteúdo de teste;
- interpretar erro bloqueante e aviso;
- substituir e revogar;
- consultar histórico e proveniência;
- cadastrar e rotacionar consumidor;
- reconhecer tentativa de exposição de segredo;
- acionar suporte e incidente;
- confirmar que exemplos de evento não substituem contrato da fonte.
