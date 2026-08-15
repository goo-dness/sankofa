from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Corrected imports based on your project structure
from app.database import get_db
from models.relations_type import (
    RelationshipTypes,  # Assuming 'models' is importable from sankofa root
)
from schemas.relations_type import (  # Assuming 'schemas' is importable from sankofa root
    RelationshipsTypeCreate,
    RelationshipsTypeRead,
)

router = APIRouter(
    prefix="/relationship_types",
    tags=["relationship_types"],
)


@router.post(
    "/", response_model=RelationshipsTypeRead, status_code=status.HTTP_201_CREATED
)
def create_relationship_type(
    relationship_type: RelationshipsTypeCreate, db: Session = Depends(get_db)
):
    """
    Create a new relationship type.

    - **name**: Canonical name of the relationship type (required, must be unique).
    - **label**: Human readable label (optional).
    - **domain**: Domain this relationship belongs to (optional).
    - **description**: Explanation of the relationship (optional).
    """
    # Check if a relationship type with this name already exists
    db_relationship_type = (
        db.query(RelationshipTypes)
        .filter(RelationshipTypes.name == relationship_type.name)
        .first()
    )
    if db_relationship_type:
        raise HTTPException(
            status_code=400,
            detail="Relationship type with this name already registered",
        )

    # Create the new relationship type
    db_relationship_type = RelationshipTypes(**relationship_type.model_dump())
    db.add(db_relationship_type)
    db.commit()
    db.refresh(db_relationship_type)
    return db_relationship_type


@router.get("/", response_model=List[RelationshipsTypeRead])
def read_relationship_types(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Retrieve a list of all relationship types.

    - **skip**: Number of relationship types to skip (for pagination).
    - **limit**: Maximum number of relationship types to return (for pagination).
    """
    relationship_types = db.query(RelationshipTypes).offset(skip).limit(limit).all()
    return relationship_types


@router.get("/{type_id}", response_model=RelationshipsTypeRead)
def read_relationship_type(type_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single relationship type by its ID.

    - **type_id**: The ID of the relationship type to retrieve.
    """
    db_relationship_type = (
        db.query(RelationshipTypes).filter(RelationshipTypes.id == type_id).first()
    )
    if db_relationship_type is None:
        raise HTTPException(status_code=404, detail="Relationship type not found")
    return db_relationship_type


@router.get("/by_name/{name}", response_model=RelationshipsTypeRead)
def read_relationship_type_by_name(name: str, db: Session = Depends(get_db)):
    """
    Retrieve a single relationship type by its name.

    - **name**: The name of the relationship type to retrieve.
    """
    db_relationship_type = (
        db.query(RelationshipTypes).filter(RelationshipTypes.name == name).first()
    )
    if db_relationship_type is None:
        raise HTTPException(status_code=404, detail="Relationship type not found")
    return db_relationship_type


@router.put("/{type_id}", response_model=RelationshipsTypeRead)
def update_relationship_type(
    type_id: int,
    relationship_type: RelationshipsTypeCreate,
    db: Session = Depends(get_db),
):
    """
    Update an existing relationship type by its ID.

    - **type_id**: The ID of the relationship type to update.
    - **name**: New canonical name (required).
    - **label**: New human readable label (optional).
    - **domain**: New domain (optional).
    - **description**: New explanation (optional).
    """
    db_relationship_type = (
        db.query(RelationshipTypes).filter(RelationshipTypes.id == type_id).first()
    )
    if db_relationship_type is None:
        raise HTTPException(status_code=404, detail="Relationship type not found")

    # Check for name conflict if name is being updated
    if relationship_type.name and relationship_type.name != db_relationship_type.name:
        existing_name_type = (
            db.query(RelationshipTypes)
            .filter(RelationshipTypes.name == relationship_type.name)
            .first()
        )
        if existing_name_type:
            raise HTTPException(
                status_code=400,
                detail="Relationship type with this name already exists",
            )

    for key, value in relationship_type.model_dump(exclude_unset=True).items():
        setattr(db_relationship_type, key, value)

    db.add(db_relationship_type)
    db.commit()
    db.refresh(db_relationship_type)
    return db_relationship_type


@router.delete("/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_relationship_type(type_id: int, db: Session = Depends(get_db)):
    """
    Delete a relationship type by its ID.

    - **type_id**: The ID of the relationship type to delete.
    """
    db_relationship_type = (
        db.query(RelationshipTypes).filter(RelationshipTypes.id == type_id).first()
    )
    if db_relationship_type is None:
        raise HTTPException(status_code=404, detail="Relationship type not found")

    db.delete(db_relationship_type)
    db.commit()
    return {"message": "Relationship type deleted successfully"}
