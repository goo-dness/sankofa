import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String

from app.database import Base


class RelationshipType(enum.Enum):
    # vocabulary for symbolic reasoning
    causes = "causes"
    treats = "treats"
    traditionally_use = "traditionally_use"
    inhibits = "inhibits"
    encodes = "encodes"
    prevalent_in = "prevalent_in"
    studied_by = "studied_by"
    corresponds_to = "corresponds_to"
    occured_in = "occured_in"
    clinically_treats = "clinically_treats"
    transmitted_by = "transmitted_by"
    risk_factor_for = "risk_factor_for"
    prevents = "prevents"
    targets = "targets"
    associated_with = "associated_with"
    resistant_to = "resistant_to"
    derived_from = "derived_from"
    variant_of = "variant_of"
    vector_of = "vector_of"
    produces = "prodces"
    documented_in = "documented_in"
    complicates = "complicates"
    progresses_to = "progresses_to"


class EntityRelations(Base):
    __tablename__ = "entity_relations"
    id = Column(Integer, primary_key=True, index=True)
    from_entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False)
    to_entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False)
    relationships = Column(Enum(RelationshipType), nullable=False)
    confidence = Column(Integer, nullable=False, default=1)
    context = Column(String)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
