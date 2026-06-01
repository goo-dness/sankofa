# app/models/relationship_types.py

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class RelationshipsType(Base):
    # this line tells SQLAlchemy which table this model maps to
    __tablename__ = "relationship_types"

    id = Column(Integer, primary_key=True, index=True)

    # the value stored in entity_relationships e.g "risk_factor_for"
    name = Column(String, nullable=False, unique=True)

    # human readable label e.g "Risk Factor For"
    label = Column(String, nullable=False)

    # which domain this relationship belongs to e.g "epidemiology"
    domain = Column(String, nullable=False)

    # explains what this relationship means
    description = Column(String)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
