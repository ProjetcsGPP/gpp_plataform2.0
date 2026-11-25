# Tratamento no frontend quando o IAM está indisponível

**Escopo:** Carga Org/Lot e Publicações Institucionais no piloto de processos
separados; Portal autenticado e API pública de Publicações.
**Estado:** contrato implementado e ensaiado nos perfis opt-in. Os perfis
separados ainda não substituíram a execução monolítica. Este documento não
autoriza cutover.
**Revisão:** 2026-11-25.

## Respostas HTTP administrativas

Quando a aplicação de domínio está no ar, mas não consegue obter uma decisão
confiável do IAM para uma ação protegida, Carga e Publicações respondem com
HTTP `503` e o envelope administrativo:

```json
{
  "success": false,
  "status_code": 503,
  "errors": {
    "code": "servico_iam_indisponivel",
    "detail": "Serviço de autorização temporariamente indisponível."
  }
}
```

Isso inclui timeout, falha de conexão e resposta de decisão inválida. O erro
**não** confirma sessão expirada ou permissão revogada; o backend não limpa o
cookie por essa falha. Diferenciar dos retornos confirmados `401` com
`errors.code = "session_invalid"` e `403` com
`errors.code = "permission_denied"`. A falta do cookie da própria aplicação
produz `401`, mesmo que o IAM também esteja fora do ar.

Se o processo IAM estiver parado, rotas pertencentes a ele, como login e
`/api/accounts/*`, podem receber `502` gerado pelo proxy, sem o envelope JSON
acima. Se o processo de Carga ou Publicações estiver parado, **suas** rotas
podem receber `502`. Um `502` ou erro de rede não prova perda de sessão; o
frontend deve conferir qual operação falhou e mostrar indisponibilidade
temporária, sem converter automaticamente em `401` ou apagar cookies.

Comportamento esperado da interface:

1. Para `503` com `servico_iam_indisponivel`, manter formulário e contexto da
   tela, informar que a autorização não pôde ser confirmada e oferecer nova
   tentativa quando o serviço voltar. Não mostrar sucesso, acesso negado ou
   pedido de novo login.
2. Para `502` do proxy ou falha de rede, mostrar indisponibilidade do serviço
   acessado. A resposta pode não ser JSON; não depender de `errors.code`.
3. Preservar o fluxo normal de autenticação para um `401` **confirmado** e a
   apresentação de acesso negado para um `403` **confirmado**.
4. Não repetir automaticamente um `POST`/mutação após timeout ou `502/503`
   sem consultar o estado canônico da operação ou confirmar sua idempotência;
   uma resposta pode ter se perdido depois da aceitação do comando.

## WebSocket

Nos perfis remotos, Carga e Publicações revalidam a autorização antes de
enviar eventos e periodicamente durante a ociosidade. Uma conexão **já
estabelecida** é fechada com `1013` se o IAM ficar indisponível; `4401`
representa sessão inválida e `4403`, permissão negada. Não chegam eventos
de domínio após uma decisão falha.

Se a falha ocorrer **antes** da aceitação do WebSocket, o navegador pode
mostrar somente um handshake HTTP `403` ou um erro genérico, sem expor o
código de fechamento pretendido. Portanto, não classificar todo erro de
handshake como revogação. Manter o estado da tela, tentar reconectar com
espera progressiva e limite, e consultar a API HTTP para atualizar o estado
canônico da operação quando ela estiver disponível. O WebSocket é apenas
canal de notificação.

## Tarefas aceitas antes da falha

| Aplicação | Estado e evidência persistidos | Apresentação recomendada |
|---|---|---|
| Carga, envio de organograma | Não inicia nova ação externa; mantém `SOLICITANDO` ou `PROCESSANDO`, agenda nova verificação e registra evento `IAM_INDISPONIVEL_ATIVIDADE` com título **Aguardando autorização do IAM** e mensagem **A autorização não pôde ser revalidada. Nenhuma nova ação externa será iniciada até a comunicação ser restabelecida.** | Mostrar espera por autorização, sem afirmar revogação, falha definitiva ou envio novo à PRODEST. Usar a consulta HTTP do envio como fonte canônica. |
| Publicações, coleta mensal E-Docs | Interrompe a coleta em `ERRO`, com `codigo_erro = "IAMColetaIndisponivel"` e `mensagem_erro = "Não foi possível confirmar a autorização; a coleta foi interrompida."`; registra auditoria. Respostas da fonte já recebidas são preservadas. | Mostrar o erro da coleta; não classificá-lo como revogação nem retomar a coleta por iniciativa do navegador. Uma nova solicitação depende do fluxo administrativo. |

Uma revogação **confirmada** tem tratamento distinto. Em Publicações, por
exemplo, usa `AutorizacaoColetaRevogada`, não `IAMColetaIndisponivel`.

## Portal público

`/api/public/v1/publicacoes-institucionais/` não consulta IAM e não exige
cookie. Deve continuar funcionando se apenas o IAM parar e o processo de
Publicações estiver disponível. Se Publicações parar, o proxy pode devolver
`502`; se a aplicação responder, seus erros públicos versionados continuam
independentes do envelope administrativo. Não utilizar prévia administrativa
ou publicação antiga como fallback automático para uma vigente indisponível.

## Aceite de integração frontend

- Simular `503` com `servico_iam_indisponivel` nas duas apps: mensagem
  temporária, formulário preservado, sem logout e sem repetição automática de
  mutação.
- Simular `401`, `403`, `502` sem JSON e falha de rede separadamente.
- Simular fechamento WebSocket `1013` e falha de handshake sem código legível;
  verificar reconexão limitada e reconciliação por HTTP.
- Exibir a espera de Carga e o `ERRO` de coleta E-Docs conforme o recurso
  canônico, mesmo se a notificação WebSocket não chegar.
- Confirmar que o Portal público não depende do IAM e não usa endpoint
  administrativo como fallback.

## Evidências no backend

- Guardas HTTP: `apps/carga_org_lot/permissoes_iam.py` e
  `apps/pub_institucional/permissoes_iam.py`; envelope em
  `common/exceptions.py`.
- WebSockets: `apps/carga_org_lot/consumers.py` e
  `apps/pub_institucional/consumidores.py`.
- Atividades: `apps/carga_org_lot/tasks.py` e
  `apps/pub_institucional/services/edocs_mensal.py`.
- Ensaio entre processos: `apps/accounts/tests/test_isolamento_publicacoes_asgi_proxy.py`;
  detalhes do piloto em [BACKEND_PUBLICACOES_ISOLAMENTO_PILOTO.md](./BACKEND_PUBLICACOES_ISOLAMENTO_PILOTO.md).
