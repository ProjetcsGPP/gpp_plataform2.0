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
- mantém o bypass global vigente nas demais aplicações;
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

Se for adotada dupla aprovação, os passos 8 e 9 exigirão pessoa diferente da
que preparou o candidato.

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
