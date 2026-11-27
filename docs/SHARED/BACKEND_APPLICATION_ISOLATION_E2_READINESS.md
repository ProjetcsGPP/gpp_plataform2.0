# E2 — Vivacidade, prontidão e dependências

**Revisão:** 2026-11-27. **Estado:** primeiro incremento implementado nos
perfis piloto e no monólito; não autoriza trocar o proxy ou ativar os perfis.

## Contrato HTTP local

| Rota | Significado | Resposta |
| --- | --- | --- |
| `GET /api/health/` | Vivacidade do processo HTTP; não consulta banco, IAM ou fonte externa. | `200`, `status: "ok"` e `service` existente. |
| `GET /api/ready/` | Prontidão local: executa `SELECT 1` no banco configurado para o processo. | `200`, `status: "pronto"`, ou `503`, `status: "indisponivel"`; sempre inclui `service`. |

Ambas as respostas usam `Cache-Control: no-store` e dispensam sessão. A nova
rota aceita apenas GET/HEAD, não publica exceção ou detalhes de conexão e
registra falha com identificador do serviço e da dependência, sem `conninfo`.
Os perfis piloto retornam `service` igual a `plataforma`, `carga_org_lot` ou
`pub_institucional`; o monólito mantém `gpp_plataform2`. No proxy TLS
**alternativo** de três processos, `/api/ready/` chega ao IAM/plataforma,
`/api/carga-org-lot/ready/` chega à Carga e
`/api/pub-institucional/ready/` chega a Publicações. O proxy em uso não foi
alterado.

O IAM **não** é critério da prontidão global de Carga ou Publicações: em
Publicações, isso retiraria a API pública do ar quando apenas a autorização
administrativa estivesse indisponível. Prontidão não é autorização e não
deve ser consultada antes de cada ação. O cliente de domínio continua a
consultar a decisão IAM da operação protegida, com timeout de conexão/leitura
de 1/2 segundos, sem retry automático e com falha fechada. `401` e `403`
dependem de decisão confirmada; falha de IAM retorna `503
servico_iam_indisponivel`, preservando sessão e contexto. Se o processo de
destino estiver parado, o proxy pode retornar `502` sem JSON. A API pública
de Publicações não chama o IAM. O contrato detalhado para a interface está em
[FRONTEND_IAM_INDISPONIBILIDADE.md](./FRONTEND_IAM_INDISPONIBILIDADE.md).

## Dependências ainda não cobertas pelo sinal de prontidão

- Broker/filas: uma indisponibilidade pode impedir tarefas novas sem impedir
  leituras HTTP; necessita métrica e alerta próprios, não derrubar todas as
  rotas pelo mesmo sinal.
- IAM: observar disponibilidade e latência por serviço consumidor, sem usar
  o ping como substituto da decisão de autorização.
- E-Docs, PRODEST, E-Flow e demais fontes: o status pertence à operação e à
  auditoria correspondente; não realizar chamadas externas em probes HTTP.
- Prazo máximo de conexão do banco para o probe e exposição individual pelo
  proxy: ainda precisam de limite e ensaio operacional antes do cutover.

## Evidência e próximos gates

Em 27/11/2026, 57 testes de saúde, prontidão e autorização IAM de Carga e
Publicações passaram em `test_gpp_plataform`. Além deles, dois ensaios do
proxy TLS temporário passaram: falha fechada com IAM parado, preservando a
API pública e a prontidão de Publicações, e reinício individual com `502`
apenas para a aplicação parada. Os testes de prontidão cobrem
os cinco URLConfs, banco disponível e indisponível, ausência de resolução do
cadastro IAM, cookie inválido, GET/HEAD, resposta sem detalhe sensível e
rejeição de POST. `manage.py check` passou no monólito e nos perfis piloto
de Carga, Publicações e plataforma separada. Pylint dos arquivos
novos/alterados passou com 10/10. Ainda faltam queda real do banco,
prontidão na topologia operacional futura, métricas/alertas de dependências
e ensaio completo de WebSocket já estabelecido sob queda do IAM nesta
rodada. Os ensaios anteriores não são reclassificados como evidência nova.

## Saída segura dos testes

O `pytest.ini` agora usa traceback de uma linha por padrão: um traceback
completo do driver PostgreSQL pode imprimir a senha embutida no `conninfo`.
Um ensaio de falha de conexão com senha **sintética** confirmou que o valor
não aparece na saída. A alteração não apaga a saída histórica já produzida
nem substitui política de segredos. Por decisão do responsável, não haverá
troca da senha do banco nesta etapa.
