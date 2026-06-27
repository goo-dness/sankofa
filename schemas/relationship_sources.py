from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RelationshipSourceBase(BaseModel):
    relationship_id: Optional[int] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    confidence: Optional[int] = None
    context: Optional[str] = None


class RelationshipSourceCreate(RelationshipSourceBase):
    pass


class RelationshipSourceRead(RelationshipSourceBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
