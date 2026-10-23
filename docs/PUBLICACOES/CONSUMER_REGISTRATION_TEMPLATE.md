# Modelo de Cadastro de Aplicação Consumidora

> Usar para consumidores internos ou externos da API de distribuição. A
> identidade de máquina é separada da `Aplicacao` usada por usuários e roles.

## 1. Identificação

| Campo | Preenchimento |
|---|---|
| Nome do sistema | |
| Código interno proposto | |
| Organização/unidade | |
| Aplicação navegável relacionada, se houver | |
| Ambiente | Desenvolvimento / Homologação / Produção |
| Responsável funcional | |
| Responsável técnico | |
| Contato de incidente | |
| Finalidade do consumo | |

## 2. Dados e contrato

| Recurso | Escopo solicitado | Finalidade | Volume/frequência |
|---|---|---|---|
| | | | |

- Versão da API:
- Campos necessários:
- Retenção no consumidor:
- Redistribuição permitida:
- SLA esperado:

## 3. Credencial e rede

| Item | Definição |
|---|---|
| Método | OAuth2 Client Credentials / chave opaca provisória / outro aprovado |
| Expiração | |
| Rotação | |
| Quota | |
| Rate limit | |
| IP/rede, quando aplicável | |
| Canal de entrega inicial | |

O segredo nunca deve ser incluído neste documento. Registrar apenas o
identificador/prefixo após a emissão.

## 4. Segurança e responsabilidade

- [ ] Escopos mínimos aprovados.
- [ ] Responsável aceita proteger e rotacionar a credencial.
- [ ] Canal seguro de entrega definido.
- [ ] Procedimento de comprometimento conhecido.
- [ ] Retenção e descarte no consumidor aprovados.
- [ ] Uso e anomalias serão monitorados.
- [ ] Teste de revogação planejado.
- [ ] Termos de uso aceitos.

## 5. Ativação

1. cadastro aprovado;
2. consumidor criado sem segredo em claro persistido;
3. credencial emitida e exibida uma única vez;
4. entrega confirmada por canal seguro;
5. chamada de homologação aprovada;
6. quotas e alertas conferidos;
7. produção habilitada;
8. data de revisão registrada.

## 6. Rotação, suspensão e encerramento

- Próxima revisão:
- Próxima rotação:
- Critério de suspensão automática:
- Procedimento de revogação emergencial:
- Procedimento de encerramento e descarte:

## 7. Aprovações

| Papel | Nome | Decisão | Data | Evidência |
|---|---|---|---|---|
| Responsável do consumidor | | | | |
| Gestão de publicações | | | | |
| Segurança, quando aplicável | | | | |

