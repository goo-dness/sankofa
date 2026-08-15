from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EntitySourcesBase(BaseModel):
    entity_id: Optional[int] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    source_author: Optional[str] = None
    source_title: Optional[str] = None
    access_at: Optional[datetime] = None


class EntitySourcesCreate(EntitySourcesBase):
    pass


class EntitySourcesRead(EntitySourcesBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
