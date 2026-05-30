from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EntityNamesBase(BaseModel):
    entity_id: int
    name: Optional[str] = None
    language: Optional[str] = None


class EntityNamesCreate(EntityNamesBase):
    pass


class EntityNamesRead(EntityNamesBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
