# Ambiente de desenvolvimento de `PUBLICACOES`

**Status:** em revisão após identificação da infraestrutura já existente  
**Data:** 2026-10-27  
**Escopo:** somente desenvolvimento; não define produtos de HML ou PRD

## Princípio

O ambiente local define contratos que os ambientes futuros deverão cumprir,
sem obrigá-los a usar os mesmos produtos:

- PostgreSQL e schema isolado para persistência;
- API S3 para objetos privados, quarentena e objetos aprovados;
- interface externa para segredos;
- fila compatível com Celery;
- cache compartilhado;
- proxy HTTP com TLS local, limites e headers;
- scanner antimalware com falha fechada;
- logs estruturados e redigidos;
- rede de desenvolvimento sem acesso externo irrestrito.

HML e PRD poderão trocar qualquer implementação se preservarem o contrato,
passarem pelos mesmos testes e tiverem seus próprios ADRs.

Os contratos normativos dos controles, e não os produtos desta stack, estão em
[`SECURITY_CONTROL_CONTRACTS.md`](./SECURITY_CONTROL_CONTRACTS.md).

## Stack local proposta

| Componente | Finalidade | Escolha de DEV | Licença/custo do software |
|---|---|---|---|
| Docker Engine + Compose | Executar a infraestrutura local de forma reproduzível | Manter a instalação Linux existente | Engine/Moby sob Apache-2.0; não usar Docker Desktop governamental sem licença comercial. |
| PostgreSQL 16 | Dados canônicos, workflow, auditoria e metadados | Usar a instância on-premises já configurada para o backend; container permanece apenas como sandbox opcional até decisão final | PostgreSQL License, permissiva e sem taxa. |
| Redis 7.2.16 | Broker Celery e Channels | Executar em container; substitui o 7.0.15 local sem suporte upstream | Redis até 7.2 usa BSD-3-Clause; não atualizar de faixa sem nova análise. |
| Memcached 1.6.x | Cache e throttling compartilhados | Manter a linha existente, limitada à rede interna | BSD; sem taxa. |
| Celery 5.6.x | Coleta, scan, cálculo e publicação assíncronos | Já presente no ambiente Python | BSD-3-Clause; sem taxa. |
| SeaweedFS | Object storage local via S3 | Proposta no lugar de MinIO novo | Apache-2.0; edição enterprise opcional e paga. |
| ClamAV | Análise antimalware de uploads | Container/serviço local com assinaturas atualizadas | GPL-2.0; sem taxa de licença; exige recursos locais. |
| OpenBao | Segredos fora de `.env` e do banco funcional | Serviço local persistente, acessível só pela rede interna | MPL-2.0; sem taxa de licença. |
| Nginx Open Source | Reverse proxy, TLS local, limites e headers | Proxy único de entrada no Compose | BSD-2-Clause; sem taxa; NGINX Plus é produto separado e pago. |
| Logs JSON + testes | Redação e correlação local | `stdout`/arquivo local inicialmente | Sem produto adicional; coletor de HML/PRD será definido depois. |

### Produtos não escolhidos para DEV

- **Docker Desktop:** entidades governamentais precisam de assinatura paga. No
  Linux será usado Docker Engine, sem Docker Desktop.
- **MinIO:** embora AGPLv3 possa ser usada sem taxa quando suas obrigações são
  atendidas, a distribuição comunitária passou a ser source-only e o
  repositório foi arquivado em 2026. Não é a escolha proposta para um ambiente
  novo.
- **HashiCorp Vault 1.15+:** usa BSL 1.1. O uso interno é permitido pelo grant
  atual, mas não é uma licença open source permissiva. OpenBao evita essa
  restrição no ambiente local.
- **Redis 7.4:** usa RSALv2/SSPLv1. Redis 8 inclui também AGPLv3. Para evitar
  mudança involuntária de obrigações, DEV permanece fixado em Redis 7.2.16 até
  uma decisão de atualização ou adoção de alternativa compatível.

Licença sem taxa não significa suporte, hospedagem ou operação sem custo. A
análise jurídica institucional continua necessária antes de HML/PRD ou de
redistribuição de imagens.

## Topologia local

```text
browser/frontend
      |
    nginx
      |
    django -------- postgresql
      |  \---------- memcached
      |  \---------- openbao
      |
    redis --------- celery worker
                       |  |  |
                       |  |  +-- serviço externo simulado
                       |  +----- clamav
                       +-------- storage S3
```

O PostgreSQL, Redis, Memcached, OpenBao, ClamAV e as portas administrativas do
storage não serão publicados para a rede externa. Apenas o Nginx e, quando
necessário, o frontend local terão portas no host.

## Reavaliação do PostgreSQL

O backend já usa em DEV uma instância PostgreSQL on-premises configurada por
`DB_HOST`, `DB_PORT`, `DB_NAME` e `DB_USER`. O serviço PostgreSQL criado no
Compose não substituiu essa instância: somente o settings especial
`config.settings.test_publicacoes_dev` aponta para `127.0.0.1:55432`.

O container permitiu executar testes destrutivos, privilégios mínimos e
backup/restore sem tocar o banco existente. Entretanto, seus resultados não
comprovam versão, backup, privilégios ou recuperação da instância on-premises.
Por isso ele não é requisito permanente nem evidência suficiente do banco real.

A direção preferida é:

1. manter a instância existente como banco de DEV da aplicação;
2. levantar com seu responsável os privilégios, backup e recuperação reais;
3. manter o container, se ainda útil, apenas como sandbox opcional iniciada sob
   demanda, nunca como segundo banco obrigatório da aplicação;
4. não migrar nem copiar dados por suposição.

A remoção ou conversão do serviço para um profile opcional depende de decisão
explícita, pois o volume local e os testes atuais ainda o utilizam.

## Regras do Compose

- imagens com versão e digest fixados; nunca `latest`;
- volumes nomeados separados;
- healthchecks e dependências por condição de saúde;
- rede de entrada separada da rede interna;
- rede dos workers marcada como interna e APIs externas representadas por mock;
- credenciais de bootstrap locais fora do Git e com permissão restrita;
- limites de CPU, memória, processos e tamanho de logs;
- containers sem root, sem modo privilegiado e com filesystem somente leitura
  sempre que o produto permitir;
- bucket `quarantine` separado de `approved`, ambos privados;
- arquivo só muda para `approved` depois de scan válido;
- script único de subida, preflight, teste e destruição dos dados locais.

## Pendência local já comprovada

Docker Engine e Compose estão instalados, mas esta sessão não conseguiu acessar
`/var/run/docker.sock`. Antes de criar o Compose, deve-se verificar fora do
sandbox se é uma restrição da sessão ou uma permissão real. Se for permissão da
estação, deve-se escolher uma das opções:

1. configurar Docker rootless para o usuário de desenvolvimento; ou
2. conceder acesso controlado ao grupo `docker`, reconhecendo que ele equivale
   praticamente a privilégio de root.

Rootless é a opção preferida para a estação de desenvolvimento quando todas as
imagens selecionadas forem compatíveis.

## Gate para o primeiro teste sintético

O primeiro teste só começa quando:

- esta proposta estiver aprovada;
- Docker estiver acessível pelo usuário sem improviso inseguro;
- Compose subir todos os serviços com healthcheck;
- versões, digests, licenças e SBOM estiverem registrados;
- banco/schema/role e buckets privados tiverem sido criados;
- ClamAV aceitar arquivo limpo e rejeitar EICAR;
- workflow manter uma suspeita simulada em quarentena e prosseguir somente após
  ordem justificada do gestor para o mesmo hash;
- OpenBao entregar um segredo de teste sem registrá-lo em log;
- worker não alcançar destinos externos não simulados;
- Nginx aplicar TLS local, limites e headers esperados;
- backup e restauração locais forem exercitados;
- suíte existente de autenticação, CSRF, cookies e autorização continuar
  passando.

O teste sintético validará este ambiente. Ele não substituirá nenhuma dessas
condições.

## Fontes de licença

- Docker Engine e Docker Desktop: <https://docs.docker.com/engine/install/> e
  <https://docs.docker.com/subscription-billing/desktop-license/>
- PostgreSQL: <https://www.postgresql.org/about/licence/>
- Redis: <https://redis.io/legal/licenses/>
- Memcached: <https://github.com/memcached/memcached>
- SeaweedFS: <https://github.com/seaweedfs/seaweedfs>
- ClamAV: <https://docs.clamav.net/Introduction.html>
- OpenBao: <https://github.com/openbao/openbao>
- Vault: <https://github.com/hashicorp/vault/blob/main/LICENSE>
- Nginx: <https://nginx.org/>
- MinIO: <https://github.com/minio/minio>
