from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class RelationshipsTypeBase(BaseModel):
    name: str
    label: Optional[str] = None
    domain: Optional[str] = None
    description: Optional[str] = None


class RelationshipsTypeCreate(RelationshipsTypeBase):
    pass


class RelationshipsTypeRead(RelationshipsTypeBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
