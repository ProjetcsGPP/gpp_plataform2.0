# Plano de Rollback — `PUBLICACOES` e novo Portal

**Versão inicial:** 2026-10-26  
**Escopo:** Fases 1 a 3; integrações reais exigirão extensão própria  
**Princípio:** rollback não exclui publicação, snapshot, artefato ou auditoria

## Controles prévios obrigatórios

- mudanças aditivas e migrations reversíveis enquanto não houver dado real;
- flags independentes para app administrativa e API/Portal públicos;
- tela anterior de login preservada até homologação do Portal público;
- publicação e histórico não dependem do cache para consistência;
- purge de cache executável e observável;
- backup e restore validados antes do go-live.

Nomes propostos das flags, a confirmar na implementação:

- backend: `PUBLICACOES_ENABLED` e `PUBLICACOES_PUBLIC_API_ENABLED`;
- frontend/server: `PUBLIC_PORTAL_ENABLED`;
- integrações: uma flag por fonte, desabilitada por padrão.

Flags que controlam segurança e exposição serão server-side. Não dependerão
exclusivamente de `NEXT_PUBLIC_*` ou de estado manipulável no browser.

## Rollback por fase

### Fase 1 — Fundação administrativa

1. desabilitar `PUBLICACOES_ENABLED` e remover menus/capabilities distribuídos;
2. manter tabelas e auditoria intactas;
3. reverter código e migration somente se a migration reversa tiver sido
   exercitada e não houver dado que precise ser preservado;
4. se houver dado, aplicar migration corretiva aditiva, nunca `DROP` manual.

### Fase 2 — Workflow manual

1. bloquear novas transições sensíveis;
2. preservar publicação e histórico existentes;
3. exportar evidência reproduzível do estado antes da correção;
4. corrigir por nova versão ou migration aditiva;
5. nunca editar ou apagar diretamente uma versão publicada.

### Fase 3 — API pública e Portal

1. desabilitar `PUBLIC_PORTAL_ENABLED` e restaurar a entrada anterior de login;
2. desabilitar `PUBLICACOES_PUBLIC_API_ENABLED` se houver risco de vazamento;
3. purgar gateway, CDN, Next.js e caches HTTP do ponteiro vigente;
4. manter endpoints administrativos disponíveis apenas se forem seguros;
5. preservar UUIDs, versões e auditoria para posterior retomada;
6. publicar estado de indisponibilidade controlado, sem servir conteúdo
   revogado ou preview como fallback.

## Gatilhos de rollback

- campo não público ou rascunho exposto;
- mistura de sessão/cache ou vazamento entre requisições SSR;
- bypass de workflow ou autorização;
- publicação vigente incorreta ou revogada ainda distribuída;
- erro de migration com risco de integridade;
- indisponibilidade sustentada além do SLA aprovado;
- segredo exposto ou suspeita de comprometimento.

## Evidência exigida antes do go-live

- exercício de desligamento de cada flag;
- migration forward/reverse em cópia descartável;
- restore de banco e artefatos medido contra RPO/RTO;
- purge completo e simulação de falha parcial;
- retorno da rota `/portal/login` anterior;
- comprovação de que rollback não apaga auditoria;
- responsáveis, contatos e autoridade para acionar o rollback.

SLA, RPO, RTO, responsáveis e ferramentas de backup/purge continuam pendentes
em `PUB-022`; por isso este plano define o processo, mas ainda não encerra o
gate operacional da Fase 0.
