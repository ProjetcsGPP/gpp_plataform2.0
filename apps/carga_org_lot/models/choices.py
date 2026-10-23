"""Estados e classificações compartilhados pela aplicação Carga Org/Lat."""

from django.db import models


class FaseProcessoCargaInicial(models.TextChoices):
    NOVO = "NOVO", "Novo"
    PREPARANDO_ORGANOGRAMA = "PREPARANDO_ORGANOGRAMA", "Preparando organograma"
    PREPARANDO_LOTACOES = "PREPARANDO_LOTACOES", "Preparando lotações"
    PRONTO_PARA_SIMULACAO = "PRONTO_PARA_SIMULACAO", "Pronto para simulação"
    SIMULANDO = "SIMULANDO", "Simulando"
    PRONTO_PARA_ENVIO = "PRONTO_PARA_ENVIO", "Pronto para envio"
    ENVIANDO = "ENVIANDO", "Enviando"
    CONCLUIDO = "CONCLUIDO", "Concluído"


class StatusOrganogramaProcesso(models.TextChoices):
    NAO_INICIADO = "NAO_INICIADO", "Não iniciado"
    EM_PREPARACAO = "EM_PREPARACAO", "Em preparação"
    EM_VALIDACAO = "EM_VALIDACAO", "Em validação"
    COM_PENDENCIAS = "COM_PENDENCIAS", "Com pendências"
    PRONTO = "PRONTO", "Pronto"
    PROCESSANDO_NA_PRODEST = "PROCESSANDO_NA_PRODEST", "Processando na PRODEST"
    CONCLUIDO = "CONCLUIDO", "Concluído"
    ERRO = "ERRO", "Erro"


class StatusLotacaoProcesso(models.TextChoices):
    BLOQUEADA = "BLOQUEADA", "Bloqueada"
    NAO_INICIADA = "NAO_INICIADA", "Não iniciada"
    EM_PREPARACAO = "EM_PREPARACAO", "Em preparação"
    EM_VALIDACAO = "EM_VALIDACAO", "Em validação"
    COM_PENDENCIAS = "COM_PENDENCIAS", "Com pendências"
    DESATUALIZADA = "DESATUALIZADA", "Desatualizada"
    PRONTA = "PRONTA", "Pronta"
    PROCESSANDO_NA_PRODEST = "PROCESSANDO_NA_PRODEST", "Processando na PRODEST"
    CONCLUIDA = "CONCLUIDA", "Concluída"
    ERRO = "ERRO", "Erro"


class StatusImportacaoLocal(models.TextChoices):
    RECEBIDA = "RECEBIDA", "Recebida"
    PROCESSANDO = "PROCESSANDO", "Processando"
    ANALISANDO_CARGOS = "ANALISANDO_CARGOS", "Analisando cargos"
    AGUARDANDO_REVISAO_CARGOS = (
        "AGUARDANDO_REVISAO_CARGOS",
        "Aguardando revisão de cargos",
    )
    AGUARDANDO_REVISAO = "AGUARDANDO_REVISAO", "Aguardando revisão"
    PRONTA_PARA_INCORPORAR = (
        "PRONTA_PARA_INCORPORAR",
        "Pronta para incorporar",
    )
    INCORPORANDO = "INCORPORANDO", "Incorporando"
    SEM_REGISTROS_VALIDOS = "SEM_REGISTROS_VALIDOS", "Sem registros válidos"
    REJEITADA = "REJEITADA", "Rejeitada"
    VALIDADA = "VALIDADA", "Validada"
    INCORPORADA = "INCORPORADA", "Incorporada"
    ALTERADA = "ALTERADA", "Alterada"
    SUBSTITUIDA = "SUBSTITUIDA", "Substituída"
    ERRO_PROCESSAMENTO = "ERRO_PROCESSAMENTO", "Erro de processamento"


class ResultadoRelatorioValidacao(models.TextChoices):
    VALIDO = "VALIDO", "Válido"
    COM_AVISOS = "COM_AVISOS", "Com avisos"
    INVALIDO = "INVALIDO", "Inválido"
    ERRO_PROCESSAMENTO = "ERRO_PROCESSAMENTO", "Erro de processamento"


class SeveridadeOcorrenciaValidacao(models.TextChoices):
    ERRO = "ERRO", "Erro"
    AVISO = "AVISO", "Aviso"
    INFORMACAO = "INFORMACAO", "Informação"
    NORMALIZACAO = "NORMALIZACAO", "Normalização"


class StatusItemLotacaoImportado(models.TextChoices):
    ACEITO = "ACEITO", "Aceito"
    COM_AVISOS = "COM_AVISOS", "Com avisos"
    COM_ERROS = "COM_ERROS", "Com erros"
    CORRIGIDO = "CORRIGIDO", "Corrigido"
    DESCARTADO = "DESCARTADO", "Descartado"
    INCORPORADO = "INCORPORADO", "Incorporado"


class StatusCasoValidacao(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    ACEITO_COMO_INFORMADO = "ACEITO_COMO_INFORMADO", "Aceito como informado"
    CORRIGIDO = "CORRIGIDO", "Corrigido"
    SUGESTAO_APLICADA = "SUGESTAO_APLICADA", "Sugestão aplicada"
    LINHAS_DESCARTADAS = "LINHAS_DESCARTADAS", "Linhas descartadas"


class AcaoResolucaoValidacao(models.TextChoices):
    ACEITAR_COMO_INFORMADO = (
        "ACEITAR_COMO_INFORMADO",
        "Aceitar como informado",
    )
    CORRIGIR_MANUALMENTE = "CORRIGIR_MANUALMENTE", "Corrigir manualmente"
    APLICAR_SUGESTAO = "APLICAR_SUGESTAO", "Aplicar sugestão"
    DESCARTAR_LINHAS = "DESCARTAR_LINHAS", "Descartar linhas"


class StatusCargoReferencia(models.TextChoices):
    NOVO = "NOVO", "Novo"
    CONFIRMADO = "CONFIRMADO", "Confirmado"
    INATIVO = "INATIVO", "Inativo"


class StatusVariacaoCargo(models.TextChoices):
    NOVA = "NOVA", "Nova"
    EM_ANALISE = "EM_ANALISE", "Em análise"
    CONFIRMADA = "CONFIRMADA", "Confirmada"
    AMBIGUA = "AMBIGUA", "Ambígua"
    IGNORADA = "IGNORADA", "Ignorada"


class EscopoMapeamentoCargo(models.TextChoices):
    GLOBAL = "GLOBAL", "Global"
    PATRIARCA = "PATRIARCA", "Somente este patriarca"
    IMPORTACAO = "IMPORTACAO", "Somente esta importação"


class SituacaoConjuntoLotacao(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    EM_VALIDACAO = "EM_VALIDACAO", "Em validação"
    COM_PENDENCIAS = "COM_PENDENCIAS", "Com pendências"
    PRONTO_PARA_HOMOLOGACAO = (
        "PRONTO_PARA_HOMOLOGACAO",
        "Pronto para homologação",
    )
    HOMOLOGADO = "HOMOLOGADO", "Homologado"
    ATIVO = "ATIVO", "Ativo"
    CANCELADO = "CANCELADO", "Cancelado"
    SUBSTITUIDO = "SUBSTITUIDO", "Substituído"


class TipoOperacaoImportacaoLotacao(models.TextChoices):
    INICIAL = "INICIAL", "Importação inicial"
    ACRESCIMO = "ACRESCIMO", "Acréscimo"
    SUBSTITUICAO = "SUBSTITUICAO", "Substituição"


class StatusEnvioOrganograma(models.TextChoices):
    SOLICITANDO = "SOLICITANDO", "Solicitando"
    PROCESSANDO = "PROCESSANDO", "Processando na PRODEST"
    CONCLUIDO = "CONCLUIDO", "Concluído"
    CONCLUIDO_DESATUALIZADO = (
        "CONCLUIDO_DESATUALIZADO",
        "Concluído, mas a origem foi alterada",
    )
    ERRO = "ERRO", "Erro"


class OperacaoIntegracaoProdest(models.TextChoices):
    FLUXO_OPERACIONAL = "FLUXO_OPERACIONAL", "Fluxo operacional"
    OBTER_TOKEN = "OBTER_TOKEN", "Autenticação no Acesso Cidadão"
    TESTAR_CONEXAO = "TESTAR_CONEXAO", "Teste de conexão"
    ENVIAR_ORGANOGRAMA_INICIAL = (
        "ENVIAR_ORGANOGRAMA_INICIAL",
        "Envio inicial do organograma",
    )
    CONSULTAR_STATUS = "CONSULTAR_STATUS", "Consulta do processamento"
    CONSULTAR_RELATORIO = "CONSULTAR_RELATORIO", "Consulta do relatório"
    LISTAR_CARGAS_INICIAIS = (
        "LISTAR_CARGAS_INICIAIS",
        "Consulta de cargas iniciais anteriores",
    )


class ResultadoIntegracaoProdest(models.TextChoices):
    SUCESSO = "SUCESSO", "Concluída"
    ERRO_HTTP = "ERRO_HTTP", "Recusada pelo serviço externo"
    TIMEOUT = "TIMEOUT", "Tempo limite excedido"
    ERRO_CONEXAO = "ERRO_CONEXAO", "Falha de comunicação"


class VisibilidadeEventoIntegracao(models.TextChoices):
    TECNICA = "TECNICA", "Técnica"
    OPERACIONAL = "OPERACIONAL", "Operacional"


class TipoCargaIntegracao(models.TextChoices):
    ORGANOGRAMA = "ORGANOGRAMA", "Organograma"
    LOTACAO = "LOTACAO", "Lotação"


class FaseIntegracaoProdest(models.TextChoices):
    PREPARACAO = "PREPARACAO", "Preparação"
    AUTENTICACAO = "AUTENTICACAO", "Autenticação"
    ENVIO = "ENVIO", "Envio"
    PROCESSAMENTO = "PROCESSAMENTO", "Processamento"
    RELATORIO = "RELATORIO", "Relatório"
    CONCLUSAO = "CONCLUSAO", "Conclusão"


class StatusEventoOperacional(models.TextChoices):
    AGUARDANDO = "AGUARDANDO", "Aguardando"
    EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
    SUCESSO = "SUCESSO", "Concluída"
    AVISO = "AVISO", "Aviso"
    ERRO = "ERRO", "Erro"
    IGNORADO = "IGNORADO", "Ignorado"
