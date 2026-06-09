import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, SessionLocal, engine
from data.relationship_types import relationship_types_data
from models.relations_type import RelationshipTypes

Base.metadata.create_all(bind=engine)


def seed_relationship_types():
    db = SessionLocal()
    try:
        for relationship in relationship_types_data:
            exists = (
                db.query(RelationshipTypes)
                .filter(RelationshipTypes.name == relationship["name"])
                .first()
            )
            if exists:
                for key, value in relationship.items():
                    setattr(exists, key, value)
            else:
                db.add(RelationshipTypes(**relationship))

        db.commit()
        print("Relationship types seeded sucessfully.")
    except Exception as e:
        print(f"Error seeding relationship types: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_relationship_types()
