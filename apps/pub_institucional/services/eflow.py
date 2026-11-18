"""Importação auditável das definições disponíveis do E-Flow."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.pub_institucional.models import (ColetaEflow, DefinicaoFluxoEflow,
                                           EventoAuditoriaEflow,
                                           EventoAuditoriaPreferenciaEflow,
                                           PatriarcaEdocs, PerfilCalculoEflow,
                                           PreferenciaExibicaoEflow,
                                           PublicoAlvoEflow,
                                           ResultadoCalculoEflow,
                                           SituacaoColetaEflow,
                                           TipoEventoAuditoriaEflow,
                                           TipoEventoAuditoriaPreferenciaEflow)

logger = logging.getLogger(__name__)

CABECALHO_EFLOW = (
    "ID",
    "Nome",
    "Versão",
    "Público-alvo",
    "Patriarca",
    "Órgão",
    "Setor",
)


class ErroValidacaoEflow(ValueError):
    """Arquivo E-Flow incompatível com o contrato conhecido."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo


@dataclass(frozen=True)
class AtorAuditoriaEflow:
    usuario_id: int | None = None
    nome: str = "sistema"


def _valores_auditoria(ator: AtorAuditoriaEflow) -> dict:
    return {
        "criado_por_id": ator.usuario_id,
        "criado_por_nome": ator.nome,
        "atualizado_por_id": ator.usuario_id,
        "atualizado_por_nome": ator.nome,
    }


def _valores_atualizacao(ator: AtorAuditoriaEflow) -> dict:
    return {
        "atualizado_por_id": ator.usuario_id,
        "atualizado_por_nome": ator.nome,
    }


def _evento_preferencia(
    preferencia,
    ator,
    tipo_evento,
    perfil_anterior,
    perfil_atual,
):
    return EventoAuditoriaPreferenciaEflow.objects.create(
        preferencia=preferencia,
        tipo_evento=tipo_evento,
        perfil_anterior=perfil_anterior,
        perfil_atual=perfil_atual,
        **_valores_auditoria(ator),
    )


@transaction.atomic
def obter_preferencia_exibicao_eflow(
    usuario,
    *,
    ator: AtorAuditoriaEflow,
) -> PreferenciaExibicaoEflow:
    """Obtém ou inicializa a preferência individual com auditoria."""

    preferencia, criada = PreferenciaExibicaoEflow.objects.get_or_create(
        usuario=usuario,
        defaults={
            "perfil_preferido": PerfilCalculoEflow.CONSOLIDADO_PUBLICACAO,
            **_valores_auditoria(ator),
        },
    )
    if criada:
        _evento_preferencia(
            preferencia,
            ator,
            TipoEventoAuditoriaPreferenciaEflow.PREFERENCIA_INICIALIZADA,
            None,
            preferencia.perfil_preferido,
        )
        logger.info(
            "EFLOW_PREFERENCE_INITIALIZED user_id=%s profile=%s",
            usuario.pk,
            preferencia.perfil_preferido,
        )
    return preferencia


@transaction.atomic
def alterar_preferencia_exibicao_eflow(
    usuario,
    *,
    perfil_preferido: str,
    ator: AtorAuditoriaEflow,
) -> PreferenciaExibicaoEflow:
    """Altera somente a preferência do usuário e preserva seu histórico."""

    if perfil_preferido not in PerfilCalculoEflow.values:
        raise ErroValidacaoEflow(
            "PERFIL_CALCULO_INVALIDO",
            "O perfil de cálculo E-Flow não é reconhecido.",
        )
    preferencia = obter_preferencia_exibicao_eflow(usuario, ator=ator)
    preferencia = PreferenciaExibicaoEflow.objects.select_for_update().get(
        pk=preferencia.pk
    )
    perfil_anterior = preferencia.perfil_preferido
    if perfil_anterior == perfil_preferido:
        return preferencia

    preferencia.perfil_preferido = perfil_preferido
    for campo, valor in _valores_atualizacao(ator).items():
        setattr(preferencia, campo, valor)
    preferencia.save()
    _evento_preferencia(
        preferencia,
        ator,
        TipoEventoAuditoriaPreferenciaEflow.PREFERENCIA_ALTERADA,
        perfil_anterior,
        perfil_preferido,
    )
    logger.info(
        "EFLOW_PREFERENCE_CHANGED user_id=%s from=%s to=%s actor_id=%s",
        usuario.pk,
        perfil_anterior,
        perfil_preferido,
        ator.usuario_id,
    )
    return preferencia


def _percentual(quantidade: int, total: int) -> str:
    valor = (Decimal(quantidade) * Decimal(100) / Decimal(total)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    return format(valor, ".2f")


def _texto(registro: dict, campo: str, limite: int) -> str:
    valor = registro.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        raise ErroValidacaoEflow(
            "CAMPO_OBRIGATORIO_AUSENTE",
            f"O campo {campo} deve ser preenchido em todas as linhas.",
        )
    normalizado = valor.strip()
    if len(normalizado) > limite:
        raise ErroValidacaoEflow(
            "CAMPO_ACIMA_DO_LIMITE",
            f"O campo {campo} excede o tamanho máximo aceito.",
        )
    return normalizado


def _ler_registros(conteudo: bytes) -> list[dict]:
    if not conteudo:
        raise ErroValidacaoEflow("ARQUIVO_VAZIO", "O arquivo E-Flow está vazio.")
    if b"\x00" in conteudo:
        raise ErroValidacaoEflow(
            "ARQUIVO_INVALIDO",
            "O arquivo E-Flow contém bytes inválidos.",
        )
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ErroValidacaoEflow(
            "ENCODING_INVALIDO",
            "O arquivo E-Flow deve usar UTF-8.",
        ) from exc

    leitor = csv.DictReader(io.StringIO(texto, newline=""), delimiter=";")
    if tuple(leitor.fieldnames or ()) != CABECALHO_EFLOW:
        raise ErroValidacaoEflow(
            "CABECALHO_INVALIDO",
            "O cabeçalho do arquivo E-Flow não corresponde ao contrato esperado.",
        )
    registros = list(leitor)
    if not registros:
        raise ErroValidacaoEflow(
            "ARQUIVO_SEM_REGISTROS",
            "O arquivo E-Flow não possui registros de dados.",
        )
    if len(registros) > settings.GPP_EFLOW_CSV_MAX_ROWS:
        raise ErroValidacaoEflow(
            "LIMITE_DE_REGISTROS_EXCEDIDO",
            "O arquivo E-Flow excede a quantidade máxima de registros.",
        )
    if any(None in registro for registro in registros):
        raise ErroValidacaoEflow(
            "QUANTIDADE_COLUNAS_INVALIDA",
            "Uma ou mais linhas possuem colunas além do cabeçalho esperado.",
        )
    return registros


def _normalizar_registros(registros: list[dict]) -> tuple[list[dict], dict]:
    normalizados = []
    ids = set()
    siglas = set()

    for numero_linha, registro in enumerate(registros, start=2):
        try:
            id_externo = UUID(_texto(registro, "ID", 36))
        except (ValueError, AttributeError) as exc:
            raise ErroValidacaoEflow(
                "ID_INVALIDO",
                f"A linha {numero_linha} possui ID inválido.",
            ) from exc
        if id_externo in ids:
            raise ErroValidacaoEflow(
                "ID_DUPLICADO",
                f"A linha {numero_linha} repete um ID já informado.",
            )
        ids.add(id_externo)

        versao_texto = _texto(registro, "Versão", 20)
        try:
            versao = int(versao_texto)
        except ValueError as exc:
            raise ErroValidacaoEflow(
                "VERSAO_INVALIDA",
                f"A linha {numero_linha} possui versão inválida.",
            ) from exc
        if versao <= 0:
            raise ErroValidacaoEflow(
                "VERSAO_INVALIDA",
                f"A linha {numero_linha} possui versão inválida.",
            )

        publico_alvo = _texto(registro, "Público-alvo", 30)
        if publico_alvo not in PublicoAlvoEflow.values:
            raise ErroValidacaoEflow(
                "PUBLICO_ALVO_DESCONHECIDO",
                f"A linha {numero_linha} possui público-alvo desconhecido.",
            )

        patriarca_texto = _texto(registro, "Patriarca", 300)
        sigla = patriarca_texto.split(" - ", maxsplit=1)[0].strip()
        if not sigla:
            raise ErroValidacaoEflow(
                "PATRIARCA_INVALIDO",
                f"A linha {numero_linha} não identifica o patriarca.",
            )
        siglas.add(sigla)
        normalizados.append(
            {
                "id_externo": id_externo,
                "nome": _texto(registro, "Nome", 500),
                "versao_origem": versao,
                "publico_alvo": publico_alvo,
                "sigla_patriarca": sigla,
                "patriarca_texto": patriarca_texto,
                "orgao": _texto(registro, "Órgão", 500),
                "setor": _texto(registro, "Setor", 500),
            }
        )

    encontrados = defaultdict(list)
    for patriarca in PatriarcaEdocs.objects.filter(sigla__in=siglas):
        encontrados[patriarca.sigla].append(patriarca)
    ausentes = sorted(siglas - encontrados.keys())
    ambiguos = sorted(sigla for sigla, itens in encontrados.items() if len(itens) != 1)
    if ausentes or ambiguos:
        detalhes = []
        if ausentes:
            detalhes.append("ausentes: " + ", ".join(ausentes))
        if ambiguos:
            detalhes.append("ambíguos: " + ", ".join(ambiguos))
        raise ErroValidacaoEflow(
            "PATRIARCA_NAO_RECONCILIADO",
            "Não foi possível reconciliar patriarcas do E-Flow ("
            + "; ".join(detalhes)
            + ").",
        )

    for registro in normalizados:
        registro["patriarca"] = encontrados[registro.pop("sigla_patriarca")][0]

    return normalizados, _calcular_indicadores(
        normalizados,
        PerfilCalculoEflow.COMPLETO_TECNICO,
    )


def _calcular_indicadores(normalizados: list[dict], perfil: str) -> dict:
    """Calcula um dos dois perfis fechados sobre o mesmo snapshot."""

    total = len(normalizados)
    if perfil == PerfilCalculoEflow.COMPLETO_TECNICO:
        orgaos = Counter(
            (registro["patriarca_texto"], registro["orgao"])
            for registro in normalizados
        )
        setores = {
            (
                registro["patriarca_texto"],
                registro["orgao"],
                registro["setor"],
            )
            for registro in normalizados
        }
        publicos_exibidos = list(PublicoAlvoEflow.values)
    elif perfil == PerfilCalculoEflow.CONSOLIDADO_PUBLICACAO:
        orgaos = Counter(registro["orgao"] for registro in normalizados)
        setores = {registro["setor"] for registro in normalizados}
        publicos_exibidos = [
            PublicoAlvoEflow.CIDADAO,
            PublicoAlvoEflow.ORGAO,
            PublicoAlvoEflow.PATRIARCA,
        ]
    else:
        raise ValueError(f"Perfil de cálculo E-Flow desconhecido: {perfil}")

    publicos = Counter(registro["publico_alvo"] for registro in normalizados)
    maiores = sorted(
        orgaos.items(),
        key=lambda item: (-item[1], str(item[0])),
    )[:5]
    quantidade_maiores = sum(quantidade for _, quantidade in maiores)
    denominador_orgaos = (
        total
        if perfil == PerfilCalculoEflow.COMPLETO_TECNICO
        else quantidade_maiores
    )
    orgaos_maiores = []
    for identidade, quantidade in maiores:
        if isinstance(identidade, tuple):
            patriarca, orgao = identidade
        else:
            patriarca, orgao = None, identidade
        orgaos_maiores.append(
            {
                "patriarca": patriarca,
                "orgao": orgao,
                "quantidade_fluxos": quantidade,
                "percentual": _percentual(quantidade, denominador_orgaos),
            }
        )

    if perfil == PerfilCalculoEflow.COMPLETO_TECNICO:
        quantidade_outros = total - quantidade_maiores
        if quantidade_outros:
            orgaos_maiores.append(
                {
                    "patriarca": None,
                    "orgao": "Outros",
                    "quantidade_fluxos": quantidade_outros,
                    "percentual": _percentual(quantidade_outros, total),
                }
            )

    total_publicos_exibidos = sum(publicos[item] for item in publicos_exibidos)
    distribuicao = [
        {
            "publico_alvo": publico_alvo,
            "quantidade_fluxos": publicos[publico_alvo],
            "percentual": _percentual(
                publicos[publico_alvo],
                total
                if perfil == PerfilCalculoEflow.COMPLETO_TECNICO
                else total_publicos_exibidos,
            ),
        }
        for publico_alvo in publicos_exibidos
        if publicos[publico_alvo]
    ]
    return {
        "quantidade_fluxos": total,
        "quantidade_orgaos_participantes": len(orgaos),
        "quantidade_setores_ativos": len(setores),
        "orgaos_maior_quantidade_fluxos": orgaos_maiores,
        "distribuicao_publico_alvo": distribuicao,
    }


def calcular_indicadores_eflow_filtrados(
    coleta: ColetaEflow,
    *,
    perfil: str,
    patriarcas_ids: list[int] | None = None,
) -> dict:
    """Filtra o snapshot antes de recalcular totais, Top 5 e percentuais."""

    definicoes = coleta.definicoes.all()
    if patriarcas_ids is not None:
        definicoes = definicoes.filter(patriarca_id__in=patriarcas_ids)
    registros = list(
        definicoes.values(
            "patriarca_texto",
            "orgao",
            "setor",
            "publico_alvo",
        )
    )
    if not registros:
        raise ErroValidacaoEflow(
            "VISAO_SEM_DEFINICOES",
            "A visão não possui definições E-Flow na coleta selecionada.",
        )
    return _calcular_indicadores(registros, perfil)


def calcular_indicadores_eflow_por_municipio(
    coleta: ColetaEflow,
    *,
    perfil: str,
    patriarcas_ids: list[int] | None = None,
) -> dict[int, dict]:
    """Calcula indicadores apenas para municípios com definições no snapshot."""

    definicoes = coleta.definicoes.filter(patriarca__codigo_municipio__isnull=False)
    if patriarcas_ids is not None:
        definicoes = definicoes.filter(patriarca_id__in=patriarcas_ids)
    por_municipio = {}
    for registro in definicoes.values(
        "patriarca__codigo_municipio",
        "patriarca_texto",
        "orgao",
        "setor",
        "publico_alvo",
    ):
        codigo = registro.pop("patriarca__codigo_municipio")
        por_municipio.setdefault(codigo, []).append(registro)
    return {
        codigo: _calcular_indicadores(registros, perfil)
        for codigo, registros in por_municipio.items()
    }


def garantir_resultados_calculo_eflow(
    coleta: ColetaEflow,
    *,
    ator: AtorAuditoriaEflow,
) -> list[ResultadoCalculoEflow]:
    """Cria os dois resultados ausentes sem reescrever resultados existentes."""

    registros = list(
        coleta.definicoes.values(
            "patriarca_texto",
            "orgao",
            "setor",
            "publico_alvo",
        )
    )
    if not registros:
        raise ErroValidacaoEflow(
            "COLETA_SEM_DEFINICOES",
            "A coleta E-Flow não possui definições para cálculo.",
        )

    resultados = []
    perfis_criados = []
    calculado_em = timezone.now()
    for perfil in PerfilCalculoEflow.values:
        indicadores = _calcular_indicadores(registros, perfil)
        resultado, criado = ResultadoCalculoEflow.objects.get_or_create(
            coleta=coleta,
            perfil=perfil,
            defaults={
                **indicadores,
                "calculado_em": calculado_em,
                **_valores_auditoria(ator),
            },
        )
        resultados.append(resultado)
        if criado:
            perfis_criados.append(perfil)
    if perfis_criados:
        _evento(
            coleta,
            ator,
            TipoEventoAuditoriaEflow.RESULTADOS_CALCULADOS,
            "Os perfis de cálculo E-Flow foram gerados.",
            {"perfis": perfis_criados},
        )
    return resultados


def _evento(coleta, ator, tipo_evento, mensagem, metadados=None):
    return EventoAuditoriaEflow.objects.create(
        coleta=coleta,
        tipo_evento=tipo_evento,
        mensagem=mensagem,
        metadados=metadados or {},
        **_valores_auditoria(ator),
    )


def _marcar_falha(coleta, ator, codigo, mensagem):
    coleta.situacao = SituacaoColetaEflow.FALHOU
    coleta.concluida_em = timezone.now()
    coleta.codigo_erro = codigo
    coleta.mensagem_erro = mensagem[:500]
    for campo, valor in _valores_atualizacao(ator).items():
        setattr(coleta, campo, valor)
    coleta.save()
    _evento(
        coleta,
        ator,
        TipoEventoAuditoriaEflow.COLETA_FALHOU,
        "A importação do CSV E-Flow falhou.",
        {"codigo_erro": codigo},
    )


def importar_csv_eflow(
    *,
    nome_arquivo: str,
    conteudo: bytes,
    ator: AtorAuditoriaEflow,
    ano_vigencia_inicio: int = 2024,
    mes_vigencia_inicio: int = 1,
    vigencia_retroativa: bool = False,
) -> ColetaEflow:
    """Preserva, valida e normaliza um snapshot manual do E-Flow."""

    if ano_vigencia_inicio < 2024:
        raise ErroValidacaoEflow(
            "ANO_VIGENCIA_INVALIDO",
            "O ano inicial da vigência E-Flow deve ser igual ou posterior a 2024.",
        )
    if mes_vigencia_inicio not in range(1, 13):
        raise ErroValidacaoEflow(
            "MES_VIGENCIA_INVALIDO",
            "O mês inicial da vigência E-Flow deve estar entre 1 e 12.",
        )
    if len(conteudo) > settings.GPP_EFLOW_CSV_MAX_BYTES:
        raise ErroValidacaoEflow(
            "ARQUIVO_ACIMA_DO_LIMITE",
            "O arquivo E-Flow excede o tamanho máximo permitido.",
        )
    nome_seguro = Path(nome_arquivo).name[:255]
    if not nome_seguro.lower().endswith(".csv"):
        raise ErroValidacaoEflow(
            "EXTENSAO_INVALIDA",
            "A coleta E-Flow aceita somente arquivo CSV.",
        )
    coleta = ColetaEflow.objects.create(
        arquivo_nome=nome_seguro,
        arquivo_hash_sha256=hashlib.sha256(conteudo).hexdigest(),
        arquivo_tamanho_bytes=len(conteudo),
        arquivo_conteudo=conteudo,
        iniciada_em=timezone.now(),
        ano_vigencia_inicio=ano_vigencia_inicio,
        mes_vigencia_inicio=mes_vigencia_inicio,
        vigencia_retroativa=vigencia_retroativa,
        **_valores_auditoria(ator),
    )
    _evento(
        coleta,
        ator,
        TipoEventoAuditoriaEflow.COLETA_INICIADA,
        "Importação do CSV E-Flow iniciada.",
        {
            "ano_vigencia_inicio": ano_vigencia_inicio,
            "mes_vigencia_inicio": mes_vigencia_inicio,
            "vigencia_retroativa": vigencia_retroativa,
        },
    )

    try:
        registros = _ler_registros(conteudo)
        normalizados, indicadores = _normalizar_registros(registros)
        with transaction.atomic():
            DefinicaoFluxoEflow.objects.bulk_create(
                [
                    DefinicaoFluxoEflow(
                        coleta=coleta,
                        **registro,
                        **_valores_auditoria(ator),
                    )
                    for registro in normalizados
                ],
                batch_size=1000,
            )
            garantir_resultados_calculo_eflow(
                coleta,
                ator=ator,
            )
            for campo, valor in indicadores.items():
                setattr(coleta, campo, valor)
            coleta.situacao = SituacaoColetaEflow.CONCLUIDA
            coleta.concluida_em = timezone.now()
            for campo, valor in _valores_atualizacao(ator).items():
                setattr(coleta, campo, valor)
            coleta.save()
            _evento(
                coleta,
                ator,
                TipoEventoAuditoriaEflow.COLETA_CONCLUIDA,
                "Importação do CSV E-Flow concluída.",
                {
                    "quantidade_fluxos": coleta.quantidade_fluxos,
                    "quantidade_orgaos_participantes": (
                        coleta.quantidade_orgaos_participantes
                    ),
                    "quantidade_setores_ativos": coleta.quantidade_setores_ativos,
                },
            )
    except ErroValidacaoEflow as exc:
        _marcar_falha(coleta, ator, exc.codigo, str(exc))
    except Exception:
        logger.exception("Falha interna na importação do CSV E-Flow")
        _marcar_falha(
            coleta,
            ator,
            "ERRO_INTERNO_EFLOW",
            "A importação falhou durante o processamento interno.",
        )
    return coleta
