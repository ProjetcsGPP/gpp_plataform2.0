# Threat Model — `PUBLICACOES` e Portal

**Versão inicial:** 2026-10-26  
**Escopo:** aplicação administrativa, Portal público, integrações e artefatos  
**Referências:** `PUB-002`, `PUB-007`, `PUB-010`, `PUB-012` a `PUB-014`,
`PUB-020` e `PUB-021`

## Ativos protegidos

- conteúdo público aprovado e seu ponteiro vigente;
- rascunhos, previews, relatórios e campos não públicos;
- snapshots, planilhas e evidências de origem;
- credenciais humanas e máquina-a-máquina;
- trilha de auditoria, autoria e justificativas;
- disponibilidade e integridade dos cálculos;
- configurações de fontes, destinos e consumidores.

## Fronteiras de confiança

```text
Browser público ──> Next SSR/CSR ──> API pública ──> publicação imutável
Browser autenticado ──> Next CSR ──> API administrativa ──> workflow/auditoria
Fonte interna ──> outbox/provider ──> snapshot versionado
Fonte externa ──> egress/conector ──> quarentena ──> validação
Planilha ──> upload ──> quarentena/AV ──> parser isolado
Consumidor M2M ──> gateway ──> API de distribuição
```

Nenhuma seta autoriza consulta direta a tabela de outro domínio, transporte de
segredo ao frontend ou uso de preview como publicação vigente.

## Ameaças e controles

| ID | Ameaça | Controle obrigatório | Evidência |
|---|---|---|---|
| TM-001 | Rascunho ou campo restrito exposto publicamente | Snapshot publicado imutável e serializer por allowlist | Testes de não vazamento por estado e campo |
| TM-002 | Cache público contaminado por sessão ou preview | ADR-0005; providers separados; público invariável por cookie | Testes com cookies distintos, preview e troca de sessão |
| TM-003 | Conteúdo revogado reaparece como vigente | Purge pós-commit, TTL curto e sem `stale-if-error` no ponteiro | Teste de revogação, falha de purge e convergência |
| TM-004 | Open redirect e phishing pós-login | Allowlist central e normalização do ADR-0003 | Casos externos, `//`, backslash e encoding ambíguo |
| TM-005 | Vazamento entre requisições SSR | Adaptador server-only sem Zustand/Axios singleton/cookies | Renderizações concorrentes com identidades distintas |
| TM-006 | IDOR administrativo | Querysets por escopo, permissões por ação e autoridade backend | Testes com IDs pertencentes a outro escopo |
| TM-007 | Abuso de `PORTAL_ADMIN` | Acesso global auditado, sem bypass de workflow | Testes de invariantes e alerta de ação privilegiada |
| TM-008 | Duas publicações vigentes por concorrência | Lock/transação, restrição e precondição de versão | Testes concorrentes reais em PostgreSQL |
| TM-009 | Replay ou duplicação de evento | Outbox, `event_id`, idempotência e reconciliação | Testes de replay, perda e reordenação |
| TM-010 | SSRF por fonte externa | Destino pré-aprovado, DNS/IP validados, egress e redirect bloqueado | Testes com loopback, rede privada, DNS rebinding e redirect |
| TM-011 | Planilha maliciosa/decompression bomb | Quarentena, tipo real, AV, limites e parser isolado | Corpus malicioso e testes de recursos |
| TM-012 | Segredo em banco, API, log ou evento | Secrets manager, hash/prefixo e redação | Gitleaks, testes de serialização e captura de logs |
| TM-013 | DoS por endpoint público ou cálculo caro | Rate limit, paginação, limites, cache e pré-cálculo | Teste de carga e orçamento de recursos |
| TM-014 | Alteração de publicação imutável | Serviço transacional e bloqueio de update/delete | Testes de model/service/API |
| TM-015 | Cálculo não reproduzível | Algoritmo/versionamento, entradas e hashes registrados | Reprocessamento produz o mesmo resultado |
| TM-016 | Log expõe dado pessoal ou credencial | Logging estruturado por allowlist e retenção aprovada | Testes de redação e revisão de amostras |
| TM-017 | Dependência vulnerável ou segredo commitado | CodeQL, Trivy e Gitleaks no CI | Pipeline bloqueante e relatório sem crítico aberto |
| TM-018 | Backup inútil ou incompleto | Backup criptografado e restore periódico | Relatório de restore contra RPO/RTO |
| TM-019 | Falso positivo bloqueia arquivo legítimo ou ordem gerencial perde rastreabilidade | Quarentena, ordem justificada do gestor, histórico preservado e liberação vinculada ao mesmo hash | Testes de alerta, aprovação, registro, execução e alteração de hash |

## Regras fail-closed

- fonte sem classificação ou contrato aprovado não coleta dado real;
- arquivo sem scanner disponível permanece em quarentena;
- achado suspeito permanece em quarentena até decisão do gestor; aprovação
  justificada preserva o alerta e ordena a execução para o mesmo hash;
- destino externo não resolvido pela allowlist não recebe requisição;
- falha de validação impede transição para publicação;
- falha de auditoria impede ação editorial sensível;
- segredo não disponível não possui fallback em banco ou configuração pública;
- ausência de publicação vigente retorna estado público explícito, nunca preview;
- falha de purge não autoriza `stale-if-error` no ponteiro vigente.

## Riscos ainda sem decisão institucional

As lacunas `INF-001` a `INF-010` do inventário mantêm riscos residuais de
upload, SSRF, segredo, disponibilidade e recuperação. Elas bloqueiam também a
fundação e os testes sintéticos, conforme `PRE_IMPLEMENTATION_CHECKLIST.md`,
até decisão, provisionamento e prova dos controles correspondentes.
