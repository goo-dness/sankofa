from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.database import Base


class EntityRelations(Base):
    __tablename__ = "entity_relations"
    id = Column(Integer, primary_key=True, index=True)
    from_entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False)
    to_entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False)
    relationship_id = Column(
        Integer, ForeignKey("relationship_types.id"), nullable=False
    )
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
