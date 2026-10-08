"""TF-IDF text representation for support resources and user queries.

This module only creates vector representations. It does not rank resources or
replace the existing keyword-based intent classifier.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


RESOURCE_TEXT_FIELDS = ("name", "category", "description", "keywords")


def _field_value(resource: Any, field: str) -> str:
    """Read a resource field from either a mapping or an object."""
    if isinstance(resource, Mapping):
        value = resource.get(field)
    else:
        value = getattr(resource, field, None)
    return "" if value is None else str(value).strip()


def build_resource_text(resource: Any) -> str:
    """Build searchable text from the resource fields used for matching.

    Location, contact, language, and identifiers are intentionally excluded.
    """
    return " ".join(
        _field_value(resource, field)
        for field in RESOURCE_TEXT_FIELDS
        if _field_value(resource, field)
    )


def _clean_documents(documents: Iterable[Any]) -> list[str]:
    """Normalize a document collection and discard blank documents."""
    if isinstance(documents, str):
        documents = [documents]
    return [str(document).strip() for document in documents if document is not None and str(document).strip()]


def fit_tfidf(resource_texts: Iterable[str]) -> tuple[TfidfVectorizer, csr_matrix]:
    """Fit a TF-IDF vectorizer on resource text and return its document matrix.

    Raises:
        ValueError: if no non-empty resource text is provided or the documents
            contain no usable terms.
    """
    documents = _clean_documents(resource_texts)
    if not documents:
        raise ValueError("at least one non-empty resource document is required")

    vectorizer = TfidfVectorizer(lowercase=True)
    try:
        resource_matrix = vectorizer.fit_transform(documents)
    except ValueError as error:
        raise ValueError("resource documents must contain usable text") from error
    return vectorizer, resource_matrix


def transform_query(vectorizer: TfidfVectorizer, query: str) -> csr_matrix:
    """Transform one user query with an already-fitted TF-IDF vectorizer.

    Empty queries return a valid all-zero row with the fitted feature width.
    """
    if not isinstance(query, str) or not query.strip():
        return csr_matrix((1, len(vectorizer.vocabulary_)), dtype=float)
    return vectorizer.transform([query.strip()])


def calculate_similarity(query_vector: csr_matrix, resource_vector: csr_matrix) -> float:
    """Calculate cosine similarity between one query and one resource vector.

    TF-IDF vectors are non-negative, so the practical score range is 0 to 1:
    0 means no shared weighted terms and 1 means identical vector direction.
    Zero vectors return 0.0 rather than producing an undefined result.
    """
    score = cosine_similarity(query_vector, resource_vector)[0][0]
    return max(0.0, min(1.0, float(score)))
