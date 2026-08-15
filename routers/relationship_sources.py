from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from models.relationship_sources import RelationshipSource
from schemas.relationship_sources import (
    RelationshipSourceCreate,
    RelationshipSourceRead,
)

router = APIRouter(
    prefix="/relationship_sources",
    tags=["relationship_sources"],
)


@router.post("/", response_model=RelationshipSourceRead, status_code=status.HTTP_201_CREATED)
def create_relationship_source(
    relationship_source: RelationshipSourceCreate, db: Session = Depends(get_db)
):
    db_relationship_source = RelationshipSource(**relationship_source.model_dump())
    db.add(db_relationship_source)
    db.commit()
    db.refresh(db_relationship_source)
    return db_relationship_source


@router.get("/", response_model=List[RelationshipSourceRead])
def read_relationship_sources(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(RelationshipSource).offset(skip).limit(limit).all()


@router.get("/{source_id}", response_model=RelationshipSourceRead)
def read_relationship_source(source_id: int, db: Session = Depends(get_db)):
    db_source = (
        db.query(RelationshipSource).filter(RelationshipSource.id == source_id).first()
    )
    if db_source is None:
        raise HTTPException(status_code=404, detail="Relationship source not found")
    return db_source


@router.get("/by_relationship/{relationship_id}", response_model=List[RelationshipSourceRead])
def read_relationship_sources_for_relationship(
    relationship_id: int, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    return (
        db.query(RelationshipSource)
        .filter(RelationshipSource.relationship_id == relationship_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.put("/{source_id}", response_model=RelationshipSourceRead)
def update_relationship_source(
    source_id: int, relationship_source: RelationshipSourceCreate, db: Session = Depends(get_db)
):
    db_source = (
        db.query(RelationshipSource).filter(RelationshipSource.id == source_id).first()
    )
    if db_source is None:
        raise HTTPException(status_code=404, detail="Relationship source not found")
    for key, value in relationship_source.model_dump(exclude_unset=True).items():
        setattr(db_source, key, value)
    db.add(db_source)
    db.commit()
    db.refresh(db_source)
    return db_source


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_relationship_source(source_id: int, db: Session = Depends(get_db)):
    db_source = (
        db.query(RelationshipSource).filter(RelationshipSource.id == source_id).first()
    )
    if db_source is None:
        raise HTTPException(status_code=404, detail="Relationship source not found")
    db.delete(db_source)
    db.commit()
    return {"message": "Relationship source deleted successfully"}
