from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EntityPeopleBase(BaseModel):
    entity_id: int
    people_name: Optional[str] = None


class EntityPeopleCreate(EntityPeopleBase):
    pass


class EntityPeopleRead(EntityPeopleBase):
    id: int
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
