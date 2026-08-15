from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Corrected imports based on your project structure
from app.database import get_db
from models.entities import Entity  # Assuming 'models' is importable from sankofa root
from schemas.entities import (  # Assuming 'schemas' is importable from sankofa root
    EntityCreate,
    EntityRead,
)

router = APIRouter(
    prefix="/entities",
    tags=["entities"],
)


@router.post("/", response_model=EntityRead, status_code=status.HTTP_201_CREATED)
def create_entity(entity: EntityCreate, db: Session = Depends(get_db)):
    """
    Create a new entity.

    - **name**: Name of the entity (required).
    - **domain**: Domain of the entity (optional).
    - **entity_type**: Type of the entity (optional).
    - **region**: Region of the entity (optional).
    - **original_lang**: Original language of the entity (optional).
    - **expression**: Expression of the entity (optional).
    - **confidence**: Confidence score of the entity (optional, default 1).\n    - **contributor**: Contributor of the entity (optional).
    """
    # Check if an entity with this name already exists
    db_entity = db.query(Entity).filter(Entity.name == entity.name).first()
    if db_entity:
        raise HTTPException(
            status_code=400, detail="Entity with this name already registered"
        )

    # Create the new entity
    db_entity = Entity(**entity.model_dump())
    db.add(db_entity)
    db.commit()
    db.refresh(db_entity)
    return db_entity


@router.get("/", response_model=List[EntityRead])
def read_entities(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve a list of all entities.

    - **skip**: Number of entities to skip (for pagination).
    - **limit**: Maximum number of entities to return (for pagination).
    """
    entities = db.query(Entity).offset(skip).limit(limit).all()
    return entities


@router.get("/{entity_id}", response_model=EntityRead)
def read_entity(entity_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single entity by its ID.

    - **entity_id**: The ID of the entity to retrieve.
    """
    db_entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if db_entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return db_entity


@router.put("/{entity_id}", response_model=EntityRead)
def update_entity(entity_id: int, entity: EntityCreate, db: Session = Depends(get_db)):
    """
    Update an existing entity by its ID.

    - **entity_id**: The ID of the entity to update.
    - **name**: New name of the entity (required).
    - **domain**: New domain of the entity (optional).
    - **entity_type**: New type of the entity (optional).
    - **region**: New region of the entity (optional).
    - **original_lang**: New original language of the entity (optional).
    - **expression**: New expression of the entity (optional).
    - **confidence**: New confidence score of the entity (optional, default 1).\n    - **contributor**: New contributor of the entity (optional).
    """
    db_entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if db_entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    for key, value in entity.model_dump(exclude_unset=True).items():
        setattr(db_entity, key, value)

    db.add(db_entity)
    db.commit()
    db.refresh(db_entity)
    return db_entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity(entity_id: int, db: Session = Depends(get_db)):
    """
    Delete an entity by its ID.

    - **entity_id**: The ID of the entity to delete.
    """
    db_entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if db_entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    db.delete(db_entity)
    db.commit()
