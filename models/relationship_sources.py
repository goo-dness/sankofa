from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.database import Base


class RelationshipSource(Base):
    __tablename__ = "relationship_sources"

    id = Column(Integer, primary_key=True, index=True)
    relationship_id = Column(Integer, ForeignKey("entity_relations.id"), nullable=False)
    source_name = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    confidence = Column(Integer, nullable=False)
    context = Column(String)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
