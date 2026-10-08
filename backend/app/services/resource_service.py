# resource_service.py — Database operations for support resources
#
# Contains simple functions for creating and retrieving SupportResource rows.
# All functions accept a SQLAlchemy Session so they work cleanly with
# FastAPI's get_db() dependency and are easy to test independently.

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database.models import SupportResource


# ── Create ────────────────────────────────────────────────────────────────────

def create_resource(
    db: Session,
    name: str,
    category: str,
    description: str = None,
    location: str = None,
    contact: str = None,
    language: str = "en",
    keywords: str = None,
) -> SupportResource:
    """
    Inserts a new support resource into the database.

    Returns the saved SupportResource object (with its new id).
    Raises a RuntimeError if the database operation fails.
    """
    resource = SupportResource(
        name=name,
        category=category,
        description=description,
        location=location,
        contact=contact,
        language=language,
        keywords=keywords,
    )

    try:
        db.add(resource)
        db.commit()
        db.refresh(resource)  # loads the auto-generated id from the DB
        return resource
    except SQLAlchemyError as e:
        db.rollback()
        raise RuntimeError(f"Failed to create resource: {e}") from e


# ── Read — all ────────────────────────────────────────────────────────────────

def get_all_resources(db: Session) -> list[SupportResource]:
    """
    Returns all support resources ordered by category then name.
    Returns an empty list if no resources exist.
    """
    return (
        db.query(SupportResource)
        .order_by(SupportResource.category, SupportResource.name)
        .all()
    )


# ── Read — by category ────────────────────────────────────────────────────────

def get_resources_by_category(db: Session, category: str) -> list[SupportResource]:
    """
    Returns all resources matching the given category (case-insensitive).
    Returns an empty list if no matches are found.

    Example:
        get_resources_by_category(db, "health")
        get_resources_by_category(db, "LEGAL")   # same result
    """
    return (
        db.query(SupportResource)
        .filter(SupportResource.category.ilike(category))
        .order_by(SupportResource.name)
        .all()
    )
