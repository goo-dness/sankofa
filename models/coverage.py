from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from app.database import Base


class IngestionCoverage(Base):
    __tablename__ = "ingestion_coverage"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String, nullable=False)
    disease_name = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    relationship_type = Column(String, nullable=False)
    last_ingested_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("disease_name", "source_name", "relationship_type", name="uq_disease_source_reltype"),
    )
