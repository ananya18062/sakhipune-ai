"""Small, dependency-free infrastructure for future external data sources.

No category endpoint is selected here. Callers provide a verified endpoint in a
later task, while this module handles transport, validation, normalization, and
PostgreSQL fallback consistently.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class ExternalAPIError(RuntimeError):
    """Safe application error for external data-source failures."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.public_message = message


@dataclass(frozen=True)
class NormalizedResource:
    """Common resource format used between data sources and recommendations."""

    name: str
    category: str
    description: str = ""
    location: str = ""
    contact: str = ""
    url: str = ""
    language: str = ""
    source: str = ""
    source_type: str = "api"
    last_updated: str = ""
    is_live: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "location": self.location,
            "contact": self.contact,
            "url": self.url,
            "language": self.language,
            "source": self.source,
            "source_type": self.source_type,
            "last_updated": self.last_updated,
            "is_live": self.is_live,
        }


class BaseAPIClient:
    """GET-only client with safe, testable transport behavior."""

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 10.0,
        opener: Callable[..., Any] | None = None,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self._opener = opener or urlopen

    def get_json(
        self,
        path: str = "",
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """GET a JSON response and raise safe ExternalAPIError on failure."""
        url = urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))
        if params:
            query = urlencode({key: value for key, value in params.items() if value is not None})
            url = url + ("&" if "?" in url else "?") + query
        request = Request(url, headers={"Accept": "application/json", **(headers or {})}, method="GET")
        safe_url = urlparse(url)._replace(query="").geturl()

        try:
            with self._opener(request, timeout=self.timeout) as response:
                raw_body = response.read()
        except HTTPError as error:
            if 400 <= error.code < 500:
                logger.warning(
                    "External API client error %s for %s (request rejected by source)",
                    error.code,
                    safe_url,
                )
                raise ExternalAPIError(
                    "CLIENT_ERROR",
                    "The external data source rejected the request.",
                ) from error
            logger.warning(
                "External API server error %s for %s (source-side failure)",
                error.code,
                safe_url,
            )
            raise ExternalAPIError(
                "SERVER_ERROR",
                "The external data source is temporarily unavailable.",
            ) from error
        except TimeoutError as error:
            logger.warning("External API timed out for %s", safe_url)
            raise ExternalAPIError("TIMEOUT", "The external data source did not respond in time.") from error
        except (URLError, OSError) as error:
            logger.warning("External API connection failure for %s: %s", safe_url, type(error).__name__)
            raise ExternalAPIError("CONNECTION_ERROR", "The external data source could not be reached.") from error

        try:
            return json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            logger.warning("External API returned invalid JSON for %s", safe_url)
            raise ExternalAPIError("INVALID_JSON", "The external data source returned invalid data.") from error


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_resource(
    payload: Mapping[str, Any],
    *,
    source: str,
    source_type: str = "api",
    is_live: bool = True,
) -> NormalizedResource:
    """Validate one source record and map it to the common resource format."""
    if not isinstance(payload, Mapping):
        raise ExternalAPIError("INVALID_FORMAT", "The external data source returned an invalid record.")
    name = _text(payload.get("name"))
    category = _text(payload.get("category"))
    if not name or not category:
        raise ExternalAPIError("MISSING_FIELDS", "The external data source returned an incomplete record.")
    if source_type not in {"api", "official_data", "database"}:
        raise ValueError("source_type must be api, official_data, or database")
    return NormalizedResource(
        name=name,
        category=category,
        description=_text(payload.get("description")),
        location=_text(payload.get("location")),
        contact=_text(payload.get("contact")),
        url=_text(payload.get("url")),
        language=_text(payload.get("language")),
        source=source,
        source_type=source_type,
        last_updated=_text(payload.get("last_updated")),
        is_live=is_live,
    )


def normalize_resources(
    payload: Any,
    *,
    source: str,
    source_type: str = "api",
    is_live: bool = True,
) -> list[dict[str, Any]]:
    """Normalize a list response, accepting either a list or ``{"data": [...]}``.

    Any other top-level shape (string, number, ``None``, nested object without a
    ``data`` key that resolves to a list) is rejected with ``INVALID_FORMAT``
    rather than propagating an ``AttributeError`` or ``TypeError`` to the caller.
    """
    if not isinstance(payload, (Mapping, list)):
        raise ExternalAPIError(
            "INVALID_FORMAT",
            "The external data source returned an unexpected response type.",
        )
    records = payload.get("data") if isinstance(payload, Mapping) else payload
    if not isinstance(records, list):
        raise ExternalAPIError("INVALID_FORMAT", "The external data source returned an invalid response.")
    try:
        return [
            normalize_resource(record, source=source, source_type=source_type, is_live=is_live).as_dict()
            for record in records
        ]
    except (AttributeError, TypeError) as error:
        raise ExternalAPIError(
            "INVALID_FORMAT",
            "The external data source returned an invalid response.",
        ) from error


def fetch_with_fallback(
    client: BaseAPIClient,
    path: str,
    *,
    source: str,
    fallback_loader: Callable[[], list[Mapping[str, Any]]],
    params: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Fetch live data, then use verified database data without marking it live."""
    try:
        payload = client.get_json(path, params=params)
        return normalize_resources(payload, source=source, source_type="api", is_live=True)
    except (ExternalAPIError, ValueError):
        logger.warning("External data unavailable for %s; using database fallback", source)
        fallback_records = fallback_loader()
        return [
            normalize_resource(
                record,
                source="PostgreSQL verified data",
                source_type="database",
                is_live=False,
            ).as_dict()
            for record in fallback_records
        ]
