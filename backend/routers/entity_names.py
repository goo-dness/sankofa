from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Corrected imports based on your project structure
from app.database import get_db
from models.entity_names import (
    EntityNames,  # Assuming 'models' is importable from sankofa root
)
from schemas.entity_names import (  # Assuming 'schemas' is importable from sankofa root
    EntityNamesCreate,
    EntityNamesRead,
)

router = APIRouter(
    prefix="/entity_names",
    tags=["entity_names"],
)


@router.post("/", response_model=EntityNamesRead, status_code=status.HTTP_201_CREATED)
def create_entity_name(entity_name: EntityNamesCreate, db: Session = Depends(get_db)):
    """
    Create a new entity name.

    - **entity_id**: The ID of the entity this name belongs to (required).
    - **name**: The alternative name for the entity (optional).
    - **language**: The language of the alternative name (optional).
    """
    # Create the new entity name
    db_entity_name = EntityNames(**entity_name.model_dump())
    db.add(db_entity_name)
    db.commit()
    db.refresh(db_entity_name)
    return db_entity_name


@router.get("/", response_model=List[EntityNamesRead])
def read_entity_names(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve a list of all entity names.

    - **skip**: Number of entity names to skip (for pagination).
    - **limit**: Maximum number of entity names to return (for pagination).
    """
    entity_names = db.query(EntityNames).offset(skip).limit(limit).all()
    return entity_names


@router.get("/{entity_name_id}", response_model=EntityNamesRead)
def read_entity_name(entity_name_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single entity name by its ID.

    - **entity_name_id**: The ID of the entity name to retrieve.
    """
    db_entity_name = (
        db.query(EntityNames).filter(EntityNames.id == entity_name_id).first()
    )
    if db_entity_name is None:
        raise HTTPException(status_code=404, detail="Entity name not found")
    return db_entity_name


@router.get("/by_entity/{entity_id}", response_model=List[EntityNamesRead])
def read_entity_names_for_entity(
    entity_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Retrieve all names associated with a specific entity.

    - **entity_id**: The ID of the entity to retrieve names for.
    - **skip**: Number of entity names to skip (for pagination).
    - **limit**: Maximum number of entity names to return (for pagination).
    """
    entity_names = (
        db.query(EntityNames)
        .filter(EntityNames.entity_id == entity_id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return entity_names


@router.put("/{entity_name_id}", response_model=EntityNamesRead)
def update_entity_name(
    entity_name_id: int,
    entity_name: EntityNamesCreate,
    db: Session = Depends(get_db),
):
    """
    Update an existing entity name by its ID.

    - **entity_name_id**: The ID of the entity name to update.
    - **entity_id**: New entity ID this name belongs to (required).
    - **name**: New alternative name for the entity (optional).
    - **language**: New language of the alternative name (optional).
    """
    db_entity_name = (
        db.query(EntityNames).filter(EntityNames.id == entity_name_id).first()
    )
    if db_entity_name is None:
        raise HTTPException(status_code=404, detail="Entity name not found")

    for key, value in entity_name.model_dump(exclude_unset=True).items():
        setattr(db_entity_name, key, value)

    db.add(db_entity_name)
    db.commit()
    db.refresh(db_entity_name)
    return db_entity_name


@router.delete("/{entity_name_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity_name(entity_name_id: int, db: Session = Depends(get_db)):
    """
    Delete an entity name by its ID.

    - **entity_name_id**: The ID of the entity name to delete.
    """
    db_entity_name = (
        db.query(EntityNames).filter(EntityNames.id == entity_name_id).first()
    )
    if db_entity_name is None:
        raise HTTPException(status_code=404, detail="Entity name not found")

    db.delete(db_entity_name)
    db.commit()
    return {"message": "Entity name deleted successfully"}
