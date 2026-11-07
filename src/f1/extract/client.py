"""Cliente REST da API OpenF1."""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any, Self

import httpx

logger = logging.getLogger(__name__)


class OpenF1Error(Exception):
    """Erro base das chamadas à API."""


class ApiRequestError(OpenF1Error):
    """A chamada falhou, mas as demais ainda podem funcionar."""


class ApiAccessError(OpenF1Error):
    """A API recusou o acesso, então as demais chamadas também falhariam.

    Acontece, por exemplo, durante uma sessão ao vivo, quando a OpenF1 restringe
    todo o acesso, inclusive ao histórico, a usuários autenticados.
    """


class OpenF1Client:
    """Consulta a API com intervalo entre chamadas e novas tentativas.

    Args:
        base_url: URL base da API.
        request_interval: Intervalo mínimo entre chamadas, em segundos.
        max_retries: Quantidade de novas tentativas após a primeira chamada.
        backoff_base: Espera da primeira nova tentativa, em segundos. Dobra a cada
            tentativa, salvo quando a API informa `Retry-After`.
        timeout: Tempo limite de cada chamada, em segundos.
        transport: Transporte HTTP alternativo, usado nos testes.
        sleep: Função de espera.
        clock: Relógio monotônico.
    """

    def __init__(
        self,
        base_url: str,
        request_interval: float = 2.0,
        *,
        max_retries: int = 5,
        backoff_base: float = 2.0,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url, timeout=timeout, transport=transport
        )
        self._request_interval = request_interval
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Encerra as conexões HTTP."""
        self._http.close()

    def get(self, endpoint: str, **params: str | int) -> list[dict[str, Any]]:
        """Busca os registros de um endpoint.

        Args:
            endpoint: Nome do endpoint, como `laps`.
            **params: Filtros da consulta, como `session_key=9165`.

        Returns:
            Registros retornados. A lista é vazia quando não há resultados.

        Raises:
            ApiAccessError: Se a API recusar o acesso (401 ou 403).
            ApiRequestError: Se a chamada falhar de forma definitiva ou se as novas
                tentativas se esgotarem.
        """
        attempt = 0
        while True:
            self._wait_for_interval()
            try:
                response = self._http.get(endpoint, params=params)
            except httpx.TransportError as exc:
                failure = f"erro de rede: {exc}"
                delay = self._backoff_delay(attempt)
            else:
                if response.status_code != 429 and response.status_code < 500:
                    return self._parse(response, endpoint)
                failure = f"HTTP {response.status_code}"
                delay = _retry_after_seconds(response) or self._backoff_delay(attempt)

            if attempt >= self._max_retries:
                raise ApiRequestError(
                    f"{endpoint} {params}: {failure} após {attempt + 1} tentativas"
                )
            attempt += 1
            logger.warning(
                "%s %s: %s. Nova tentativa %d de %d em %.1f s",
                endpoint,
                params,
                failure,
                attempt,
                self._max_retries,
                delay,
            )
            self._sleep(delay)

    def _wait_for_interval(self) -> None:
        if self._last_request_at is not None:
            remaining = self._request_interval - (self._clock() - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def _backoff_delay(self, attempt: int) -> float:
        return self._backoff_base * 2**attempt

    def _parse(self, response: httpx.Response, endpoint: str) -> list[dict[str, Any]]:
        status = response.status_code
        if status in (401, 403):
            raise ApiAccessError(f"HTTP {status}: {_error_detail(response)}")
        if status == 404 and "no results" in _error_detail(response).lower():
            return []
        if status != 200:
            raise ApiRequestError(
                f"{endpoint}: HTTP {status}: {_error_detail(response)}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiRequestError(f"{endpoint}: resposta não é JSON") from exc
        if not isinstance(payload, list):
            raise ApiRequestError(f"{endpoint}: resposta não é uma lista")
        return payload


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text
    if isinstance(payload, dict) and "detail" in payload:
        return str(payload["detail"])
    return response.text


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except ValueError:
        return None
    return max((retry_at - datetime.now(UTC)).total_seconds(), 0.0)
