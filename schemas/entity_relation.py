from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from models.entity_relations import RelationshipType


class EntityRelationsBase(BaseModel):
    from_entity_id: int
    to_entity_id: Optional[int] = None
    relationships: RelationshipType
    confidence: Optional[int] = None
    context: Optional[str] = None


class EntityRelationsCreate(EntityRelationsBase):
    pass


class EntityRelationsRead(EntityRelationsBase):
    id: int
    created_at: datetime
    update_at: datetime
    model_config = ConfigDict(from_attributes=True)
