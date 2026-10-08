# models.py — SQLAlchemy ORM model for support resources
#
# Defines the `support_resources` table.
# Tables are created at app startup via Base.metadata.create_all() in main.py.

from sqlalchemy import Column, Integer, String, Text

from app.database.connection import Base


class SupportResource(Base):
    """
    Represents a single women's support resource in Pune.

    Examples of what rows will contain:
        - Emergency helplines
        - Legal aid centres
        - Healthcare facilities
        - Counselling services
        - Employment and skill-training programmes
        - Education support
        - Government schemes
        - Shelters
        - Financial support
        - Domestic violence support
    """

    __tablename__ = "support_resources"

    # Primary key — auto-incremented by PostgreSQL
    id = Column(Integer, primary_key=True, index=True)

    # Name of the resource or organisation
    name = Column(String(255), nullable=False)

    # Category, e.g. "legal", "health", "employment", "shelter"
    category = Column(String(100), nullable=False)

    # Full description of what the resource offers
    description = Column(Text, nullable=True)

    # Physical address or area in Pune
    location = Column(String(255), nullable=True)

    # Phone number, email, or website
    contact = Column(String(255), nullable=True)

    # Language the resource is available in, e.g. "en", "mr", "hi"
    language = Column(String(50), nullable=True, default="en")

    # Comma-separated keywords for matching, e.g. "job,career,skill"
    keywords = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<SupportResource id={self.id} name='{self.name}' category='{self.category}'>"
