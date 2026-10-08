import asyncio
import os
import sys

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.api import routes
from app.main import request_validation_error_handler, unexpected_error_handler
from app.models.schemas import SupportRequest, UserQuery


def response_payload(response):
    import json
    return json.loads(response.body.decode("utf-8"))


def test_empty_message_is_rejected_as_validation_error():
    with pytest.raises(ValidationError):
        SupportRequest(message="   ")


def test_invalid_category_is_rejected_as_validation_error():
    with pytest.raises(ValidationError):
        SupportRequest(message="I need support", category="not-a-category")


def test_request_validation_handler_returns_safe_shape():
    request = Request({"type": "http", "method": "POST", "path": "/recommend", "headers": []})
    response = asyncio.run(request_validation_error_handler(request, RequestValidationError([])))

    assert response.status_code == 422
    assert response_payload(response) == {
        "error": "VALIDATION_ERROR",
        "message": "Please provide a valid support request.",
    }


def test_database_failure_returns_service_unavailable(monkeypatch):
    def fail_database(_db):
        raise SQLAlchemyError("database details must stay private")

    monkeypatch.setattr(routes, "get_all_resources", fail_database)
    response = routes.recommend(SupportRequest(message="I need support"), object())

    assert response.status_code == 503
    assert response_payload(response)["error"] == "SERVICE_UNAVAILABLE"
    assert "database" not in response_payload(response)["message"].lower()


def test_nlp_failure_returns_safe_error(monkeypatch):
    def fail_nlp(_message):
        raise RuntimeError("private NLP details")

    monkeypatch.setattr(routes, "classify_intent", fail_nlp)
    response = routes.analyze_query(UserQuery(message="I need support"))

    assert response.status_code == 500
    assert response_payload(response)["error"] == "NLP_ERROR"
    assert "private" not in response_payload(response)["message"]


def test_recommendation_failure_returns_safe_error(monkeypatch):
    def fail_pipeline(*args, **kwargs):
        raise RuntimeError("private recommendation details")

    monkeypatch.setattr(routes, "get_all_resources", lambda _db: [])
    monkeypatch.setattr(routes, "run_recommendation_pipeline", fail_pipeline)
    response = routes.recommend(SupportRequest(message="I need support"), object())

    assert response.status_code == 500
    assert response_payload(response)["error"] == "RECOMMENDATION_ERROR"
    assert "private" not in response_payload(response)["message"]


def test_unexpected_handler_hides_internal_details():
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    response = asyncio.run(unexpected_error_handler(request, RuntimeError("secret")))

    assert response.status_code == 500
    assert response_payload(response) == {
        "error": "INTERNAL_ERROR",
        "message": "Something went wrong. Please try again later.",
    }
