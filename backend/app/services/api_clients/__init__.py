"""Reusable external data-source client infrastructure."""

from app.services.api_clients.base_client import (
    BaseAPIClient,
    ExternalAPIError,
    NormalizedResource,
    fetch_with_fallback,
    normalize_resource,
    normalize_resources,
)

__all__ = [
    "BaseAPIClient",
    "ExternalAPIError",
    "NormalizedResource",
    "fetch_with_fallback",
    "normalize_resource",
    "normalize_resources",
]
