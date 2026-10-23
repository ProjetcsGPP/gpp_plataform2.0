# Plano de Segurança da Aplicação `PUBLICACOES`

**Status:** baseline para threat model e gates  
**Princípio:** nenhum endpoint público ou integração real entra em produção sem
validação dos controles correspondentes

## 1. Ativos protegidos

- credenciais de usuários e sessões;
- credenciais de APIs externas e consumidores;
- artefatos brutos e planilhas;
- snapshots de fontes;
- rascunhos e publicações ainda não liberadas;
- regras e resultados de cálculo;
- trilhas de auditoria;
- disponibilidade da API e do Portal;
- integridade da indicação de “última publicação vigente”.

## 2. Fronteiras de confiança

| Fronteira | Regra mínima |
|---|---|
| Browser público → Portal/API | Sem confiança; validação, cache seguro e rate limiting |
| Browser autenticado → API administrativa | Sessão válida, CSRF, permissão técnica e auditoria |
| Aplicação interna → `PUBLICACOES` | Contrato versionado, evento idempotente e snapshot verificável |
| Sistema externo → conector | TLS, allowlist, credencial protegida e consumo defensivo |
| Arquivo → worker | Quarentena, detecção real, limites e isolamento |
| Consumidor → API de distribuição | Credencial de máquina, escopo, quota e revogação |
| Worker → rede externa | Egress mínimo e destino permitido |

## 3. Riscos prioritários antes da aplicação

### P0

- CSRF não efetivamente imposto nas views DRF autenticadas;
- sessão customizada aceita sem validar expiração e usuário ativo;
- throttle específico de login não aplicado como documentado;
- endpoint público de resolução permite distinguir usuário existente;
- decisão pendente sobre o bypass de `PORTAL_ADMIN` em ações editoriais.

### Evidência parcial da Fase 0 — 2026-10-23

O lado backend de `PUB-008` foi implementado e validado:

- autenticação cookie-based volta a impor CSRF nas views DRF autenticadas;
- login e logout seletivo também impõem CSRF explicitamente;
- `GET /api/accounts/auth/csrf/` inicializa o cookie antes do login;
- login aceita `identifier` opaco, com falha genérica para username, e-mail,
  conta inativa, senha incorreta ou e-mail ambíguo;
- o endpoint enumerável `resolve-user` foi removido do backend;
- sessões expiradas, revogadas, de usuário inativo ou com contexto divergente
  são rejeitadas;
- o login possui throttle dedicado por IP configurado por
  `LOGIN_THROTTLE_RATE`; `X-Forwarded-For` não é confiado sem configuração
  explícita de `DRF_NUM_PROXIES`;
- 25 testes específicos e a suíte completa de 1.130 testes passaram em
  PostgreSQL, com 1 teste ignorado e cobertura total de 87,46%.

O P0 continua aberto de forma transversal até o frontend adotar o bootstrap
CSRF e o login por `identifier`, remover o consumo de `resolve-user` e executar
seus testes de integração. `PUB-010` permanece pendente e independente.

### P1 da nova solução

- publicação acidental de campo restrito;
- alteração de conteúdo já publicado;
- SSRF por cadastro de fonte externa;
- arquivo malicioso ou decompression bomb;
- segredo exposto em banco, frontend, log ou evento;
- replay/duplicação de evento ou webhook;
- cálculo não reproduzível;
- cache servindo rascunho ou resposta autenticada como pública;
- abuso de API e consumo irrestrito de recursos;
- comprometimento de credencial de consumidor.

## 4. Matriz de controles

| Área | Controles obrigatórios | Evidência esperada |
|---|---|---|
| Autenticação humana | Sessão expirada/inativa rejeitada, cookie seguro, CSRF | Testes negativos e configuração de produção |
| Autorização | Permissão por ação, fail-closed, sem role hardcoded no frontend | Matriz e testes por permissão |
| Publicação | Imutabilidade, transação, histórico e justificativa | Testes de estado/concorrência |
| Dados | Classificação por campo e allowlist de serialização | Catálogo e teste de não vazamento |
| Eventos | Outbox, idempotência, retry, dead-letter e reconciliação | Testes de falha e replay |
| APIs externas | Allowlist, TLS, timeout, redirect e egress | Testes SSRF e configuração de rede |
| Upload | Quarentena, tipo real, AV, limites e nome interno | Relatório de scanner e testes maliciosos |
| Segredos | Vault/env, rotação e redação | Scan de segredo e teste de logs |
| API pública | Rate limit, paginação, cache e resposta limitada | Teste de carga e headers |
| Consumidores | Hash de segredo, escopo, quota e revogação | Testes de rotação/revogação |
| Observabilidade | Correlação, métricas, alertas e trilha auditável | Dashboards e alertas exercitados |
| Recuperação | Backup, restauração, RPO/RTO | Evidência de restore |

## 5. Checklist para cadastrar uma fonte

Nenhuma fonte entra em produção sem:

- [ ] proprietário funcional e técnico;
- [ ] finalidade e base de tratamento registradas;
- [ ] inventário e classificação dos campos;
- [ ] contrato e schema versionados;
- [ ] frequência, volume e SLA conhecidos;
- [ ] método de autenticação definido;
- [ ] segredo provisionado fora do código;
- [ ] destino em allowlist e egress autorizado;
- [ ] timeout, retry e circuit breaker definidos;
- [ ] cursor/idempotência definidos;
- [ ] política de correção e indisponibilidade;
- [ ] testes de contrato e segurança;
- [ ] responsável pela desativação;
- [ ] retenção e descarte definidos.

## 6. Checklist para cadastrar consumidor

- [ ] pessoa e unidade responsáveis;
- [ ] sistema, ambiente e finalidade;
- [ ] recursos e escopos mínimos;
- [ ] quota e limite de taxa;
- [ ] expiração e calendário de rotação;
- [ ] canal seguro para entrega inicial;
- [ ] contatos de incidente;
- [ ] termos de uso e retenção;
- [ ] teste de revogação;
- [ ] monitoramento de anomalias habilitado.

## 7. Gate por mudança

Toda mudança que altere exposição pública, permissão, credencial, ingestão ou
workflow precisa responder no PR:

1. Qual ativo ou fronteira muda?
2. Quais ameaças novas aparecem?
3. Qual controle impede ou detecta cada ameaça?
4. Como o controle foi testado?
5. Que dado pode aparecer em logs ou erros?
6. Como reverter sem perder histórico?
7. O contrato permanece compatível?

## 8. Incidentes mínimos previstos

Runbooks devem existir para:

- publicação incorreta ou com dado restrito;
- comprometimento de credencial de consumidor;
- comprometimento de credencial de fonte;
- arquivo malicioso detectado;
- indisponibilidade de fonte externa;
- fila parada ou dead-letter crescente;
- inconsistência entre evento e snapshot;
- abuso/negação de serviço na API pública;
- perda ou corrupção de publicação vigente.

## 9. Referências de segurança

- [OWASP API Security Top 10](https://api-security.owasp.org/editions/2023/en/0x11-t10/)
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749.html)
