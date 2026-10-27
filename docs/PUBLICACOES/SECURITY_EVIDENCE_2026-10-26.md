# Evidências de segurança de DEV — 2026-10-26

Este registro consolida resultados reproduzíveis do ambiente local. Ele não
aprova risco, não suprime achados e não substitui a decisão do gestor.
Relatórios integrais e SBOMs permanecem em
`infra/publicacoes-dev/runtime/security-evidence/`, fora do Git por poderem
conter detalhes específicos da estação.

## Resultado executivo

| Controle | Resultado | Evidência |
|---|---|---|
| Preflight de serviços | Aprovado | PostgreSQL, Redis, Memcached, S3, ClamAV, OpenBao, isolamento CargaRH HML/PRD, TLS, loopback, proxy, SSRF e falha fechada passaram. |
| Backup e restauração da sandbox | Aprovado com escopo limitado | Dump criptografado, restauração em banco Docker isolado e verificação do marcador passaram; isso não comprova a instância on-premises usada pelo backend. |
| Autenticação e autorização | Aprovado | 804 testes aprovados e 1 ignorado no recorte `accounts/core/portal`. |
| Regressão backend completa | Aprovado | 1.138 testes aprovados, 1 ignorado e cobertura de 87,55%, acima do mínimo de 80%. |
| Cadeia de fornecimento | Bloqueada para aceitação | Há achados altos/críticos não suprimidos em OpenBao e PostgreSQL; os três achados do Nginx foram corrigidos e o novo scan ficou zerado nessa faixa. |
| Rotação de credenciais em DEV | Não periódica por decisão | Nenhuma chave será rotacionada por calendário em DEV. Substituições exigem ação explícita; política periódica fica para HML/PRD. |

## Varredura das imagens

Ferramenta: Trivy 0.76.1, fixado por digest, com relatório integral e SBOM
CycloneDX. As quantidades abaixo são ocorrências reportadas pela ferramenta,
não uma afirmação de explorabilidade nem de falso positivo.

| Imagem | Crítico | Alto | Com versão corrigida indicada | Sem correção indicada | Situação |
|---|---:|---:|---:|---:|---|
| Redis | 0 | 0 | 0 | 0 | Sem achado alto/crítico. |
| Memcached | 0 | 0 | 0 | 0 | Sem achado alto/crítico. |
| ClamAV | 0 | 0 | 0 | 0 | Sem achado alto/crítico. |
| SeaweedFS | 0 | 0 | 0 | 0 | Um achado de severidade desconhecida permanece no relatório. |
| Nginx | 0 | 0 | 0 | 0 | Imagem derivada atualizou os três pacotes indicados; preflight e novo scan passaram. |
| OpenBao | 0 | 5 | 5 | 0 | Achados estão no binário Go; exigir release corrigida ou build controlado. |
| PostgreSQL Docker | 4 | 96 | 28 | 72 | Resultado exclusivo da sandbox opcional; não caracteriza a instância on-premises real. |

Não se usa `--ignore-unfixed` nem allowlist automática. Cada correção exige
novo SBOM, novo relatório e repetição dos contratos. Uma eventual ordem do
gestor registra justificativa, escopo e resultado separadamente do achado.

## Compatibilidade da sandbox PostgreSQL

A troca experimental do PostgreSQL Debian pela variante Alpine preservou o
volume, mas o teste de restore falhou porque o cluster existente registrou
collation de glibc e a imagem Alpine usa musl. A imagem Debian fixada anterior
foi restaurada sem apagar volumes; depois disso, preflight e restore passaram.

Portanto, migrar a sandbox para Alpine exigiria migração lógica para um cluster
novo. Esse exercício não autoriza nem orienta mudanças na instância on-premises.

## Comandos de reprodução

```bash
infra/publicacoes-dev/scripts/preflight.sh
infra/publicacoes-dev/scripts/verify-backup-restore.sh
FORCE_SECURITY_SCAN=1 infra/publicacoes-dev/scripts/security-scan.sh
infra/publicacoes-dev/scripts/bootstrap-test-runner.sh
infra/publicacoes-dev/scripts/run-backend-security-tests.sh
```

## Pendências que impedem encerrar o gate

1. validar privilégios, backup e recuperação no PostgreSQL on-premises real;
2. decidir se a sandbox Docker será mantida sob demanda ou removida;
3. corrigir ou receber ordem justificada para os achados altos/críticos;
4. comprovar egress no nível de rede, além do contrato aplicativo de SSRF;
5. completar métricas, traces, correlação e alerta local;
6. nomear responsáveis e aprovar piloto e classificação dos dados.
