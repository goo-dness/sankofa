from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Corrected imports based on your project structure
from app.database import get_db
from models.entity_people import (
    EntityPeople,  # Assuming 'models' is importable from sankofa root
)
from schemas.entity_people import (  # Assuming 'schemas' is importable from sankofa root
    EntityPeopleCreate,
    EntityPeopleRead,
)

router = APIRouter(
    prefix="/entity_people",
    tags=["entity_people"],
)


@router.post("/", response_model=EntityPeopleRead, status_code=status.HTTP_201_CREATED)
def create_entity_people(
    entity_people: EntityPeopleCreate, db: Session = Depends(get_db)
):
    """
    Create a new entity-person association.

    - **entity_id**: The ID of the entity this person is associated with (required).
    - **people_name**: The name of the African people/ethnic group (optional).
    """
    # Create the new entity-person association
    db_entity_people = EntityPeople(**entity_people.model_dump())
    db.add(db_entity_people)
    db.commit()
    db.refresh(db_entity_people)
    return db_entity_people


@router.get("/", response_model=List[EntityPeopleRead])
def read_entity_people_list(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Retrieve a list of all entity-person associations.

    - **skip**: Number of associations to skip (for pagination).
    - **limit**: Maximum number of associations to return (for pagination).
    """
    entity_people_list = db.query(EntityPeople).offset(skip).limit(limit).all()
    return entity_people_list


@router.get("/{entity_people_id}", response_model=EntityPeopleRead)
def read_entity_people(entity_people_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single entity-person association by its ID.

    - **entity_people_id**: The ID of the entity-person association to retrieve.
    """
    db_entity_people = (
        db.query(EntityPeople).filter(EntityPeople.id == entity_people_id).first()
    )
    if db_entity_people is None:
        raise HTTPException(
            status_code=404, detail="Entity-person association not found"
        )
    return db_entity_people


@router.get("/by_entity/{entity_id}", response_model=List[EntityPeopleRead])
def read_entity_people_for_entity(
    entity_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Retrieve all people associated with a specific entity.

    - **entity_id**: The ID of the entity to retrieve associated people for.
    - **skip**: Number of associations to skip (for pagination).
    - **limit**: Maximum number of associations to return (for pagination).
    """
    entity_people_list = (
        db.query(EntityPeople)
        .filter(EntityPeople.entity_id == entity_id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return entity_people_list


@router.put("/{entity_people_id}", response_model=EntityPeopleRead)
def update_entity_people(
    entity_people_id: int,
    entity_people: EntityPeopleCreate,
    db: Session = Depends(get_db),
):
    """
    Update an existing entity-person association by its ID.

    - **entity_people_id**: The ID of the entity-person association to update.
    - **entity_id**: New entity ID this association belongs to (required).
    - **people_name**: New name of the African people/ethnic group (optional).
    """
    db_entity_people = (
        db.query(EntityPeople).filter(EntityPeople.id == entity_people_id).first()
    )
    if db_entity_people is None:
        raise HTTPException(
            status_code=404, detail="Entity-person association not found"
        )

    for key, value in entity_people.model_dump(exclude_unset=True).items():
        setattr(db_entity_people, key, value)

    db.add(db_entity_people)
    db.commit()
    db.refresh(db_entity_people)
    return db_entity_people


@router.delete("/{entity_people_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity_people(entity_people_id: int, db: Session = Depends(get_db)):
    """
    Delete an entity-person association by its ID.

    - **entity_people_id**: The ID of the entity-person association to delete.
    """
    db_entity_people = (
        db.query(EntityPeople).filter(EntityPeople.id == entity_people_id).first()
    )
    if db_entity_people is None:
        raise HTTPException(
            status_code=404, detail="Entity-person association not found"
        )

    db.delete(db_entity_people)
    db.commit()
    return {"message": "Entity-person association deleted successfully"}
