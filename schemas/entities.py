from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EntityBase(BaseModel):
    name: str
    domain: Optional[str] = None
    entity_type: Optional[str] = None
    region: Optional[str] = None
    original_lang: Optional[str] = None
    expression: Optional[str] = None
    confidence: Optional[int] = None
    contributor: Optional[str] = None


class EntityCreate(EntityBase):
    pass


class EntityRead(EntityBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
