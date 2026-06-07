from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Corrected imports based on your project structure
from app.database import get_db
from models.entity_sources import (
    EntitySource,  # Assuming 'models' is importable from sankofa root
)
from schemas.entity_sources import (  # Assuming 'schemas' is importable from sankofa root
    EntitySourcesCreate,
    EntitySourcesRead,
)

router = APIRouter(
    prefix="/entity_sources",
    tags=["entity_sources"],
)


@router.post("/", response_model=EntitySourcesRead, status_code=status.HTTP_201_CREATED)
def create_entity_source(
    entity_source: EntitySourcesCreate, db: Session = Depends(get_db)
):
    """
    Create a new entity source.

    - **entity_id**: The ID of the entity this source is for (required).
    - **source_name**: Name of the source (required).
    - **source_url**: URL of the source (optional).
    - **access_at**: Timestamp of when the source was accessed (optional).
    """
    # Create the new entity source
    db_entity_source = EntitySource(**entity_source.model_dump())
    db.add(db_entity_source)
    db.commit()
    db.refresh(db_entity_source)
    return db_entity_source


@router.get("/", response_model=List[EntitySourcesRead])
def read_entity_sources(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve a list of all entity sources.

    - **skip**: Number of sources to skip (for pagination).
    - **limit**: Maximum number of sources to return (for pagination).
    """
    entity_sources = db.query(EntitySource).offset(skip).limit(limit).all()
    return entity_sources


@router.get("/{source_id}", response_model=EntitySourcesRead)
def read_entity_source(source_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single entity source by its ID.

    - **source_id**: The ID of the entity source to retrieve.
    """
    db_entity_source = (
        db.query(EntitySource).filter(EntitySource.id == source_id).first()
    )
    if db_entity_source is None:
        raise HTTPException(status_code=404, detail="Entity source not found")
    return db_entity_source


@router.get("/by_entity/{entity_id}", response_model=List[EntitySourcesRead])
def read_entity_sources_for_entity(
    entity_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Retrieve all sources associated with a specific entity.

    - **entity_id**: The ID of the entity to retrieve sources for.
    - **skip**: Number of sources to skip (for pagination).
    - **limit**: Maximum number of sources to return (for pagination).
    """
    entity_sources = (
        db.query(EntitySource)
        .filter(EntitySource.entity_id == entity_id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return entity_sources


@router.put("/{source_id}", response_model=EntitySourcesRead)
def update_entity_source(
    source_id: int, entity_source: EntitySourcesCreate, db: Session = Depends(get_db)
):
    """
    Update an existing entity source by its ID.

    - **source_id**: The ID of the entity source to update.
    - **entity_id**: New ID of the entity this source is for (required).
    - **source_name**: New name of the source (optional).
    - **source_url**: New URL of the source (optional).
    - **access_at**: New timestamp of when the source was accessed (optional).
    """
    db_entity_source = (
        db.query(EntitySource).filter(EntitySource.id == source_id).first()
    )
    if db_entity_source is None:
        raise HTTPException(status_code=404, detail="Entity source not found")

    for key, value in entity_source.model_dump(exclude_unset=True).items():
        setattr(db_entity_source, key, value)

    db.add(db_entity_source)
    db.commit()
    db.refresh(db_entity_source)
    return db_entity_source


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity_source(source_id: int, db: Session = Depends(get_db)):
    """
    Delete an entity source by its ID.

    - **source_id**: The ID of the entity source to delete.
    """
    db_entity_source = (
        db.query(EntitySource).filter(EntitySource.id == source_id).first()
    )
    if db_entity_source is None:
        raise HTTPException(status_code=404, detail="Entity source not found")

    db.delete(db_entity_source)
    db.commit()
    return {"message": "Entity source deleted successfully"}
