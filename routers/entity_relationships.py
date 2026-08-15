from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

# Corrected imports based on your project structure
from app.database import get_db
from models.entity_relationships import (
    EntityRelations,  # Assuming 'models' is importable from sankofa root
)
from schemas.entity_relationships import (  # Assuming 'schemas' is importable from sankofa root
    EntityRelationsCreate,
    EntityRelationsRead,
)

router = APIRouter(
    prefix="/entity_relations",
    tags=["entity_relations"],
)


@router.post(
    "/", response_model=EntityRelationsRead, status_code=status.HTTP_201_CREATED
)
def create_entity_relation(
    relation: EntityRelationsCreate, db: Session = Depends(get_db)
):
    """
    Create a new entity relationship.

    - **from_entity_id**: The ID of the source entity (required).
    - **to_entity_id**: The ID of the target entity (optional).
    - **relationship_id**: The ID of the relationship type (optional).
    - **confidence**: Confidence score of the relationship (optional, default 1).
    - **context**: Context or description of the relationship (optional).
    """
    # Create the new entity relationship
    db_relation = EntityRelations(**relation.model_dump())
    db.add(db_relation)
    db.commit()
    db.refresh(db_relation)
    return db_relation


@router.get("/", response_model=List[EntityRelationsRead])
def read_entity_relations(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Retrieve a list of all entity relationships.

    - **skip**: Number of relationships to skip (for pagination).
    - **limit**: Maximum number of relationships to return (for pagination).
    """
    relations = db.query(EntityRelations).offset(skip).limit(limit).all()
    return relations


@router.get("/{relation_id}", response_model=EntityRelationsRead)
def read_entity_relation(relation_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single entity relationship by its ID.

    - **relation_id**: The ID of the entity relationship to retrieve.
    """
    db_relation = (
        db.query(EntityRelations).filter(EntityRelations.id == relation_id).first()
    )
    if db_relation is None:
        raise HTTPException(status_code=404, detail="Entity relationship not found")
    return db_relation


@router.get("/by_entity/{entity_id}", response_model=List[EntityRelationsRead])
def read_entity_relations_for_entity(
    entity_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Retrieve all relationships where an entity is either the source or target.

    - **entity_id**: The ID of the entity to retrieve relationships for.
    - **skip**: Number of relationships to skip (for pagination).
    - **limit**: Maximum number of relationships to return (for pagination).
    """
    relations = (
        db.query(EntityRelations)
        .filter(
            or_(
                EntityRelations.from_entity_id == entity_id,
                EntityRelations.to_entity_id == entity_id,
            )
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    return relations


@router.put("/{relation_id}", response_model=EntityRelationsRead)
def update_entity_relation(
    relation_id: int, relation: EntityRelationsCreate, db: Session = Depends(get_db)
):
    """
    Update an existing entity relationship by its ID.

    - **relation_id**: The ID of the entity relationship to update.
    - **from_entity_id**: New ID of the source entity (required).
    - **to_entity_id**: New ID of the target entity (optional).
    - **relationship_id**: New ID of the relationship type (optional).
    - **confidence**: New confidence score (optional).
    - **context**: New context or description (optional).
    """
    db_relation = (
        db.query(EntityRelations).filter(EntityRelations.id == relation_id).first()
    )
    if db_relation is None:
        raise HTTPException(status_code=404, detail="Entity relationship not found")

    for key, value in relation.model_dump(exclude_unset=True).items():
        setattr(db_relation, key, value)

    db.add(db_relation)
    db.commit()
    db.refresh(db_relation)
    return db_relation


@router.delete("/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entity_relation(relation_id: int, db: Session = Depends(get_db)):
    """
    Delete an entity relationship by its ID.

    - **relation_id**: The ID of the entity relationship to delete.
    """
    db_relation = (
        db.query(EntityRelations).filter(EntityRelations.id == relation_id).first()
    )
    if db_relation is None:
        raise HTTPException(status_code=404, detail="Entity relationship not found")

    db.delete(db_relation)
    db.commit()
    return {"message": "Entity relationship deleted successfully"}
