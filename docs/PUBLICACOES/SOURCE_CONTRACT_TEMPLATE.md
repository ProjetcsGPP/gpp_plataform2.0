# Modelo de Contrato de Fonte

> Preencher e aprovar antes de implementar eventos, consultas ou importações de
> uma aplicação de origem. Exemplos discutidos informalmente não substituem este
> contrato.

## 1. Identificação

| Campo | Preenchimento |
|---|---|
| Código da fonte | |
| Nome | |
| Aplicação proprietária | |
| Responsável funcional | |
| Responsável técnico | |
| Contato de incidente | |
| Ambiente | Desenvolvimento / Homologação / Produção |
| Finalidade da integração | |
| Base de tratamento/classificação | |

## 2. Regra de disponibilização

Descrever com palavras do responsável da origem, sem inferência:

- Qual informação será disponibilizada?
- Em que momento ela pode ser considerada canônica?
- Qual ação ou estado indica que existe nova versão?
- Existem simulação, prévia ou estados que devem ser ignorados?
- Como correção, cancelamento, substituição ou revogação são representados?
- A origem garante ordenação ou monotonicidade de versão?
- Uma versão antiga continua reproduzível?

## 3. Mecanismo

| Item | Definição |
|---|---|
| Tipo | Provider local / API / Webhook + API / Polling / Arquivo |
| Evento ou agenda | |
| Identificador idempotente | |
| Tipo e ID do agregado | |
| Versão da origem | |
| Cursor de reconciliação | |
| Frequência/volume esperado | |
| Timeout e retry | |
| SLA da origem | |

## 4. Schema do snapshot

| Campo | Tipo | Obrigatório | Classificação | Significado | Origem/regra |
|---|---|---:|---|---|---|
| | | | Público/Gerencial/Restrito | | |

Anexar:

- JSON Schema ou contrato equivalente;
- exemplo sintético sem dado sensível;
- versão inicial do schema;
- política de compatibilidade;
- limites de tamanho e paginação.

## 5. Cálculos e responsabilidades

| Cálculo/regra | Responsável | Implementação canônica | Evidência/versionamento |
|---|---|---|---|
| | Origem/Publicações | | |

Confirmar explicitamente:

- [ ] `PUBLICACOES` não reconstruirá regra exclusiva do domínio de origem.
- [ ] O frontend não recalculará valores canônicos.
- [ ] Cálculos cruzados indicam versões de todas as fontes utilizadas.

## 6. Segurança

- [ ] Campos classificados e minimizados.
- [ ] Autenticação e autorização definidas.
- [ ] Segredo provisionado fora do código e dos models de negócio.
- [ ] Destinos e egress aprovados.
- [ ] Logs e erros redigidos.
- [ ] Idempotência e replay tratados.
- [ ] Retenção e descarte definidos.
- [ ] Testes de contrato e segurança planejados.

## 7. Falhas e recuperação

- Comportamento quando a origem estiver indisponível:
- Critério de retry e dead-letter:
- Processo de reconciliação:
- Tratamento de divergência de hash/versão:
- Procedimento para corrigir dado já utilizado:
- Responsável por reprocessamento:

## 8. Critérios de aceite

- [ ] Snapshot reproduzível por versão.
- [ ] Evento repetido não duplica resultado.
- [ ] Evento perdido é recuperado pela reconciliação.
- [ ] Indisponibilidade de `PUBLICACOES` não desfaz ação da origem.
- [ ] Campo não autorizado não aparece no DTO.
- [ ] Contrato possui testes automatizados.
- [ ] Observabilidade e alertas foram definidos.

## 9. Aprovações

| Papel | Nome | Decisão | Data | Evidência |
|---|---|---|---|---|
| Responsável funcional da origem | | | | |
| Responsável técnico da origem | | | | |
| Gestão de publicações | | | | |
| Segurança/privacidade, quando aplicável | | | | |

