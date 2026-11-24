# Infraestrutura local de `PUBLICACOES`

Este diretório provisiona somente o ambiente de desenvolvimento aprovado. As
ferramentas podem mudar em HML/PRD, mas os contratos de segurança e preflights
deverão ser repetidos.

O Nginx padrão continua apontando `/api/` para um único backend local.
O ensaio adicional de três processos (IAM, Carga e Publicações) está descrito
em [BACKEND_PUBLICACOES_ISOLAMENTO_PILOTO.md](../../docs/SHARED/BACKEND_PUBLICACOES_ISOLAMENTO_PILOTO.md).
O arquivo `compose-isolamento-tres.yaml` é opt-in e não substitui o proxy em
uso; Publicações ainda depende do banco IAM compartilhado para autorização
administrativa.
Para o ensaio **opt-in** de dois processos, há uma configuração alternativa
em `config/nginx/nginx-isolamento.conf`; consulte primeiro o
[contrato do piloto de Carga](../../docs/SHARED/BACKEND_CARGA_ISOLAMENTO_PILOTO.md).
Uma entrada TLS compartilhada pode encaminhar processos separados: não é
necessário criar um proxy por aplicação. O proxy alternativo não é ativado
automaticamente e exige teste de conectividade host-contêiner.

Na topologia local observada em 2026-11-24, `host.docker.internal` resolveu
para `172.17.0.1`, mas o backend escutava somente em `127.0.0.1:8000`; o
contêiner Nginx recebeu conexão recusada. **Não** habilitar o arquivo
alternativo acima esperando que ele alcance esse backend. Para o ensaio Linux
de processos no mesmo host, `compose-isolamento-loopback.yaml` fornece um
proxy opt-in em `https://localhost:58444`, separado do proxy padrão, com
`network_mode: host` e upstreams em loopback. Só serve API e WebSocket;
`/interno/` e o frontend não são encaminhados. Não executar esse Compose como
substituto do proxy institucional ou enquanto houver conflito de porta. O modo
host compartilha a rede do sistema e reduz o isolamento de rede do contêiner;
é uma solução de ensaio local, não a topologia final aprovada.

O PostgreSQL deste Compose é uma sandbox auxiliar de testes e não substitui a
instância on-premises configurada nos settings normais. Sua permanência está em
reavaliação. O OpenBao pode ficar parado quando o trabalho não chama integrações
que dependem do cofre; consulte
[`OPENBAO_DEV_GUIDE.md`](../../docs/PUBLICACOES/OPENBAO_DEV_GUIDE.md).

## Imagens fixadas

| Serviço | Versão |
|---|---|
| PostgreSQL | 16.15, variante Debian 12 (compatível com o volume DEV existente) |
| Redis | 7.2.16, variante Alpine 3.21 e última linha BSD-3 suportada selecionada |
| Memcached | 1.6.45, variante Alpine 3.24 |
| SeaweedFS | 4.51 |
| ClamAV | 1.5.4 |
| OpenBao | 2.7.1 |
| Nginx | 1.30.6, variante Alpine derivada; pacotes de segurança fixados no Dockerfile |

As imagens externas estão fixadas por tag e digest no `compose.yaml` ou no
`FROM` do Dockerfile derivado. A imagem local do Nginx é reproduzida pelo
Dockerfile com versões exatas dos pacotes corrigidos e recebe novo SBOM após o
build. Atualizações exigem revisão de licença, vulnerabilidades, release notes
e nova execução dos contratos.

## Inicialização

```bash
infra/publicacoes-dev/scripts/bootstrap-runtime.sh
infra/publicacoes-dev/scripts/compose.sh pull
infra/publicacoes-dev/scripts/compose.sh up -d
infra/publicacoes-dev/scripts/bootstrap-postgres.sh
infra/publicacoes-dev/scripts/bootstrap-test-runner.sh
infra/publicacoes-dev/scripts/bootstrap-openbao.sh
./.venv/bin/python infra/publicacoes-dev/scripts/provision_cargarh_secret.py --environment HML
./.venv/bin/python infra/publicacoes-dev/scripts/provision_edocs_secret.py
./.venv/bin/python infra/publicacoes-dev/scripts/provision_zimbra_secret.py
infra/publicacoes-dev/scripts/preflight.sh
infra/publicacoes-dev/scripts/verify-backup-restore.sh
infra/publicacoes-dev/scripts/security-scan.sh
infra/publicacoes-dev/scripts/run-backend-security-tests.sh
```

O primeiro comando cria credenciais aleatórias, configuração S3 e certificado
TLS em `runtime/`, diretório ignorado pelo Git. O bootstrap do OpenBao grava as
chaves de inicialização e a AppRole também nesse diretório, com modo restrito.
O bootstrap cria AppRoles distintas para CargaRH HML/PRD e para os serviços
compartilhados E-Docs e Zimbra em HML/PRD. Cada identidade lê somente seu
caminho e não possui escrita; o provisionamento administrativo é feito pelos
utilitários explícitos acima. E-Docs e Zimbra pertencem ao backend GPP como um
todo; não são recursos exclusivos de `PUBLICACOES`, embora esta seja a primeira
aplicação consumidora.

O S3 usa quatro identidades de privilégio mínimo: coleta escreve somente na
quarentena; scanner lê somente a quarentena; promoção lê a quarentena e escreve
na área aprovada; publicação lê somente a área aprovada. Nenhuma identidade da
aplicação pode criar ou excluir buckets. O cliente deve usar upload `PUT`; o
fluxo não depende de políticas por prefixo nem de upload HTML `POST`.
Uma quinta identidade administrativa existe somente para o job local e
descartável que cria os dois buckets; ela não é uma credencial da aplicação.

O Redis desativa o usuário padrão e expõe somente o usuário `publicacoes`,
limitado ao namespace `publicacoes:*`, sem categorias administrativas ou
perigosas. Ampliações de comandos devem ser justificadas por um consumidor e
incorporadas aos testes de negação do preflight.

`scripts/egress_policy.py` é o contrato executável mínimo contra SSRF. Cada
conector deverá fornecer allowlist própria, validar todos os IPs resolvidos,
conectar ao IP já validado sem nova resolução e repetir a validação em cada
redirecionamento. Uma ordem justificada do gestor poderá autorizar uma operação
concreta no workflow aplicativo, sem alterar silenciosamente esta política.

Não copie os valores de `runtime/` para `.env`, documentação, issue ou log.

## Endpoints locais

Por padrão, todos são publicados apenas em `127.0.0.1`:

| Serviço | Endpoint |
|---|---|
| PostgreSQL | `127.0.0.1:55432` |
| Redis | `127.0.0.1:56379` |
| Memcached | `127.0.0.1:51211` |
| S3 | `http://127.0.0.1:58333` |
| ClamAV | `127.0.0.1:53310` |
| OpenBao | `http://127.0.0.1:58200` |
| Entrada TLS | `https://127.0.0.1:58443` |

O certificado TLS é local, autoassinado e válido por 30 dias. Não deve ser
instalado como autoridade confiável global.

## Limites atuais

- Django e frontend continuam executando no host; o Nginx padrão **tenta**
  alcançá-los por `host.docker.internal`. A conectividade depende do endereço
  em que cada processo escuta e não é garantida para listeners em loopback.
- O preflight básico já cobre autenticação Redis, negação administrativa,
  detecção EICAR, leitura via AppRole sem escrita, separação positiva e negativa
  dos papéis S3, disponibilidade dos serviços, proxy, limites e SSRF. O teste
  de backup/restore criptografado também foi executado com sucesso.
- A varredura integral permanece bloqueante enquanto os achados altos/críticos
  de OpenBao e PostgreSQL não forem corrigidos ou objeto de ordem justificada.
  Os três achados altos do Nginx foram corrigidos na imagem derivada. Consulte
  `docs/PUBLICACOES/SECURITY_EVIDENCE_2026-10-26.md`.
- O contrato de SSRF está executável na aplicação, mas a restrição de egress no
  nível de rede ainda precisa ser comprovada.
- ClamAV precisa de saída HTTPS para atualizar assinaturas. Os serviços são
  publicados somente no loopback; a restrição de saída por contêiner não é
  garantida pelo Compose local e permanece um controle obrigatório a redefinir
  para HML/PRD.
- O ambiente não contém dados ou credenciais reais.

Para parar sem apagar volumes:

```bash
infra/publicacoes-dev/scripts/compose.sh down
```

A exclusão de volumes é destrutiva e não faz parte de nenhum script padrão.

O teste de recuperação cria uma tabela-marcador temporária, produz um dump
criptografado em `runtime/backups/`, restaura em um banco de nome fixo e isolado,
confere o conteúdo e remove somente o banco e a tabela de prova. O backup
criptografado é preservado como evidência local; a chave permanece em
`runtime/secrets/`.

O scan de cadeia de fornecimento usa Trivy 0.76.1, fixado por digest, em
contêiner isolado sem montagem do socket Docker. Para cada imagem ele gera SBOM
CycloneDX e relatório integral de vulnerabilidades em
`runtime/security-evidence/`. O Trivy é Apache-2.0 e não exige licença paga;
achados continuam registrados para tratamento ou ordem justificada do gestor.

O executor de testes cria um `PGPASSFILE` temporário e usa o papel
`gpp_test_runner`, que não é superusuário e só recebe `CREATEDB` para administrar
bancos `test_*`. O arquivo é removido ao final. A credencial administrativa não
é passada ao Django nem escrita em linha de comando.
