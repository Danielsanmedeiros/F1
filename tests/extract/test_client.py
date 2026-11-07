from collections.abc import Callable

import httpx
import pytest

from f1.extract.client import ApiAccessError, ApiRequestError, OpenF1Client

BASE_URL = "https://api.test/v1"
Handler = Callable[[httpx.Request], httpx.Response]


def make_client(handler: Handler, sleeps: list[float], **kwargs: float) -> OpenF1Client:
    return OpenF1Client(
        BASE_URL,
        request_interval=0,
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        **kwargs,
    )


def sequence(*responses: httpx.Response | Exception) -> Handler:
    pending = iter(responses)

    def handler(_: httpx.Request) -> httpx.Response:
        item = next(pending)
        if isinstance(item, Exception):
            raise item
        return item

    return handler


def test_get_retorna_registros_e_envia_filtros() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[{"lap_number": 1}])

    with make_client(handler, []) as client:
        records = client.get("laps", session_key=9165)

    assert records == [{"lap_number": 1}]
    assert str(requests[0].url) == f"{BASE_URL}/laps?session_key=9165"


def test_get_repete_apos_429_respeitando_retry_after() -> None:
    sleeps: list[float] = []
    handler = sequence(
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(200, json=[{"a": 1}]),
    )

    records = make_client(handler, sleeps).get("laps")

    assert records == [{"a": 1}]
    assert sleeps == [7.0]


def test_get_repete_apos_erro_de_rede_com_espera_crescente() -> None:
    sleeps: list[float] = []
    handler = sequence(
        httpx.ConnectError("caiu"),
        httpx.Response(503),
        httpx.Response(200, json=[]),
    )

    make_client(handler, sleeps, backoff_base=1.0).get("laps")

    assert sleeps == [1.0, 2.0]


def test_get_falha_com_5xx_persistente() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    client = make_client(handler, [], max_retries=2)

    with pytest.raises(ApiRequestError, match="HTTP 500 após 3 tentativas"):
        client.get("laps")
    assert len(calls) == 3


def test_get_aceita_lista_vazia() -> None:
    client = make_client(sequence(httpx.Response(200, json=[])), [])

    assert client.get("laps") == []


def test_get_trata_404_sem_resultados_como_vazio() -> None:
    response = httpx.Response(404, json={"detail": "No results found."})
    client = make_client(sequence(response), [])

    assert client.get("laps") == []


def test_get_falha_com_404_de_outro_tipo_sem_repetir() -> None:
    response = httpx.Response(404, json={"detail": "Not Found"})
    client = make_client(sequence(response), [])

    with pytest.raises(ApiRequestError, match="Not Found"):
        client.get("inexistente")


def test_get_interrompe_quando_sessao_ao_vivo_bloqueia_acesso() -> None:
    sleeps: list[float] = []
    response = httpx.Response(401, json={"detail": "Live F1 session in progress."})
    client = make_client(sequence(response), sleeps)

    with pytest.raises(ApiAccessError, match="Live F1 session"):
        client.get("laps")
    assert sleeps == []


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, text="<html>"), "não é JSON"),
        (httpx.Response(200, json={"a": 1}), "não é uma lista"),
    ],
)
def test_get_rejeita_resposta_inesperada(
    response: httpx.Response, message: str
) -> None:
    client = make_client(sequence(response), [])

    with pytest.raises(ApiRequestError, match=message):
        client.get("laps")


def test_get_espera_o_intervalo_entre_chamadas() -> None:
    sleeps: list[float] = []
    clock_values = iter([10.0, 10.5, 12.0])
    client = OpenF1Client(
        BASE_URL,
        request_interval=2.0,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
        sleep=sleeps.append,
        clock=lambda: next(clock_values),
    )

    client.get("laps")
    client.get("laps")

    assert sleeps == [1.5]
