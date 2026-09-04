"""Extrai viagens do riders.uber.com direto da API GraphQL que a web usa.

Substitui a leitura dos e-mails de recibo. A query `GetTrip` devolve distância,
duração, endereços e valor já estruturados, então some daqui o parsing por regex
e a dependência de o e-mail chegar (que era justamente o que não acontecia).

A autenticação são dois cookies de sessão, `sid` e `csid`, lidos de UBER_SID e
UBER_CSID. Duram cerca de um mês; quando expiram a API responde 404 e é preciso
recopiá-los do DevTools em Application > Cookies > riders.uber.com. Atenção: o
nome do cookie é minúsculo, ao contrário do nome da variável de ambiente.
"""

import base64
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import dlt
from dlt.sources.helpers.requests import Client

from config import load_config

cfg = load_config()
log = logging.getLogger(__name__)

ENDPOINT = "https://riders.uber.com/graphql"
FUSO = ZoneInfo("America/Sao_Paulo")

# O servidor capa a página em 50 mesmo quando pedimos mais: `limit: 1000` devolve
# 50 calado. Por isso a paginação é obrigatória, não uma otimização.
POR_PAGINA = 50

# Quantas viagens buscar por execução. A ~50 viagens/mês, 60 cobre um mês fechado
# com folga; o que já estiver no banco o dlt descarta pelo primary key.
PADRAO_VIAGENS = 60

ATIVIDADES = """
query Activities($endTimeMs: Float, $limit: Int,
                 $orderTypes: [RVWebCommonActivityOrderType!],
                 $profileType: RVWebCommonActivityProfileType) {
  activities {
    past(endTimeMs: $endTimeMs, limit: $limit,
         orderTypes: $orderTypes, profileType: $profileType) {
      activities { uuid subtitle description }
      nextPageToken
    }
  }
}
"""

VIAGEM = """
query GetTrip($tripUUID: String!) {
  getTrip(tripUUID: $tripUUID) {
    trip {
      uuid status beginTripTime dropoffTime fare driver
      waypoints cityID marketplace
    }
    rating
    receipt { distance distanceLabel duration vehicleType }
  }
}
"""


class SessaoExpirada(RuntimeError):
    """Os cookies foram recusados — precisa recolá-los do DevTools."""


class RespostaInesperada(RuntimeError):
    """A API respondeu fora do contrato — provável mudança de schema."""


def _abrir_sessao():
    """Sessão com retry/backoff do dlt, cookies e headers já fixos."""

    sid, csid = cfg.UBER_SID, cfg.UBER_CSID
    if not (sid and csid):
        raise SessaoExpirada("defina UBER_SID e UBER_CSID no .env")

    sessao = Client(raise_for_status=False, request_timeout=30).session
    sessao.headers.update(
        {
            "content-type": "application/json",
            "x-csrf-token": "x",
            "cookie": f"sid={sid}; csid={csid}",
        }
    )
    return sessao


def _consultar(sessao, operacao, query, variaveis):
    """Uma chamada GraphQL, separando os erros pela ação que cada um exige."""
    resposta = sessao.post(
        ENDPOINT,
        json={
            "operationName": operacao,
            "variables": variaveis,
            "query": query,
        },
    )

    if resposta.status_code == 404:
        raise SessaoExpirada(
            "a Uber recusou os cookies — recopie sid e csid do DevTools"
        )
    resposta.raise_for_status()

    corpo = resposta.json()
    # GraphQL responde 200 com `errors` quando a query não bate com o schema.
    if "errors" in corpo:
        raise RespostaInesperada(corpo["errors"][0].get("message", "erro sem mensagem"))
    return corpo["data"]


def _cursor_para_ms(token):
    """O nextPageToken é um ISO-8601 em base64 — vira o endTimeMs seguinte."""
    iso = base64.b64decode(token).decode().replace("Z", "+00:00")
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def _cancelada(atividade):
    """Canceladas aparecem como 'R$0.00 • Canceled' e não têm recibo."""
    return "Canceled" in (atividade.get("description") or "")


def listar_uuids(sessao, quantidade):
    """UUIDs das N viagens concluídas mais recentes, da mais nova pra mais velha.

    Pagina pelo `endTimeMs`, nunca pelo parâmetro `nextPageToken`: passar o token
    junto com um filtro de data devolve zero resultados sem erro, e passá-lo
    sozinho ignora o filtro. Decodificar o token e usá-lo como `endTimeMs` é o
    único jeito de paginar mantendo o intervalo — a fronteira é exclusiva, então
    não há sobreposição entre páginas.
    """
    encontrados, fim = [], None
    while len(encontrados) < quantidade:
        pagina = _consultar(
            sessao,
            "Activities",
            ATIVIDADES,
            {
                "endTimeMs": fim,
                "limit": POR_PAGINA,
                "orderTypes": ["RIDES", "TRAVEL"],
                "profileType": "PERSONAL",
            },
        )["activities"]["past"]

        atividades = pagina["activities"]
        for atividade in atividades:
            if not _cancelada(atividade):
                encontrados.append(atividade["uuid"])
                if len(encontrados) == quantidade:
                    break

        # O token vem preenchido mesmo na última página cheia, porque o servidor
        # não sabe que acabou. A página vazia é o que de fato encerra o loop.
        if not atividades or not pagina["nextPageToken"]:
            break
        fim = _cursor_para_ms(pagina["nextPageToken"])

    return encontrados


def _momento(texto):
    """Converte o Date.toString() do JS em datetime com fuso.

    'Mon Aug 31 2026 19:55:34 GMT+0000 (Coordinated Universal Time)'
    """
    if not texto:
        return None
    sem_nome_do_fuso = re.sub(r"\s*\(.*\)$", "", texto)
    return datetime.strptime(sem_nome_do_fuso, "%a %b %d %Y %H:%M:%S GMT%z")


def _dinheiro(texto):
    """'R$12.65' -> 12.65. Tolera o formato pt-BR ('R$ 1.234,56') por garantia."""
    if not texto:
        return None
    numero = re.sub(r"[^\d.,]", "", texto)
    if not numero:
        return None
    if numero.rfind(",") > numero.rfind("."):
        numero = numero.replace(".", "").replace(",", ".")
    else:
        numero = numero.replace(",", "")
    return float(numero)


def _minutos(texto):
    """'8 minutes' -> 8; '1 hour 12 minutes' -> 72."""
    if not texto:
        return None
    horas = re.search(r"(\d+)\s*h", texto)
    minutos = re.search(r"(\d+)\s*m", texto)
    total = (int(horas.group(1)) * 60 if horas else 0) + (
        int(minutos.group(1)) if minutos else 0
    )
    return total or None


def _quilometros(distancia, unidade):
    """A conta de milhas nunca dispara em BH, mas o campo `distanceLabel` existe
    justamente porque a unidade acompanha o país da viagem."""
    if not distancia:
        return None
    valor = float(distancia)
    return round(valor * 1.609344, 3) if (unidade or "").startswith("mile") else valor


def buscar_viagem(sessao, uuid):
    """Uma viagem achatada e tipada, pronta pro banco."""
    dados = _consultar(sessao, "GetTrip", VIAGEM, {"tripUUID": uuid})["getTrip"]
    viagem, recibo = dados["trip"], dados.get("receipt") or {}

    inicio, fim = _momento(viagem["beginTripTime"]), _momento(viagem["dropoffTime"])
    inicio_local = inicio.astimezone(FUSO) if inicio else None
    fim_local = fim.astimezone(FUSO) if fim else None
    trajeto = viagem.get("waypoints") or []

    return {
        "uuid": viagem["uuid"],
        "status": viagem.get("status"),
        "trip_date": inicio_local.date() if inicio_local else None,
        "time_start": inicio_local.time().replace(microsecond=0)
        if inicio_local
        else None,
        "time_end": fim_local.time().replace(microsecond=0) if fim_local else None,
        "begin_time_utc": inicio,
        "dropoff_time_utc": fim,
        "total_brl": _dinheiro(viagem.get("fare")),
        "distance_km": _quilometros(
            recibo.get("distance"), recibo.get("distanceLabel")
        ),
        "duration_min": _minutos(recibo.get("duration")),
        "from_address": trajeto[0] if trajeto else None,
        "to_address": trajeto[-1] if len(trajeto) > 1 else None,
        "product": recibo.get("vehicleType"),
        "driver": viagem.get("driver") or None,
        "driver_rating": dados.get("rating") or None,
        "city_id": viagem.get("cityID"),
        "marketplace": viagem.get("marketplace"),
    }


@dlt.resource(name="uber_trips", write_disposition="merge", primary_key="uuid")
def uber_trips(quantidade=PADRAO_VIAGENS):
    """As N viagens concluídas mais recentes.

    Reprocessar é seguro e esperado: o merge pelo `uuid` faz com que rodar duas
    vezes no mesmo mês, ou com janelas sobrepostas, não duplique nada. É o que
    permite buscar sempre um bloco fixo em vez de calcular intervalo de datas.
    """
    sessao = _abrir_sessao()
    uuids = listar_uuids(sessao, quantidade)
    log.info("Uber: %d viagens concluídas a carregar", len(uuids))

    datas = []
    for posicao, uuid in enumerate(uuids, start=1):
        viagem = buscar_viagem(sessao, uuid)
        if viagem["status"] != "COMPLETED":
            log.warning("Uber: %s veio como %s, ignorada", uuid, viagem["status"])
            continue
        datas.append(viagem["trip_date"])
        if posicao % 20 == 0:
            log.info("Uber: %d/%d", posicao, len(uuids))
        yield viagem

    # Confira esta linha depois de rodar: se a data mais antiga for posterior ao
    # início do mês que você está fechando, `quantidade` ficou curta.
    if datas:
        log.info("Uber: cobertura de %s a %s", min(datas), max(datas))
