import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, get_db
from data.relationship_types import relationship_types_data
from ingestions.who import extract_who_data, load_to_database, transform_to_entities
from models.relations_type import RelationshipTypes

Base.metadata.create_all(bind=engine)
# Define insertion parameters
WHO_INDICATOR_CODES_TO_INGEST = [
    "MALARIA_EST_INCIDENCE",
    "HIV_PREV",
    "TB_INCIDENCE",
    "CM_01"  # Child mortality
    "MMR"  # Maternal mortality rate
    "CHOLERA_TOTAL",
]
AFRICAN_COUNTRY_CODES_TO_INGEST = [
    "NGA",
    "GHA",
    "KEN",
    "ETH",
    "ZAF",
    "UGA",
    "TZA",
    "CMR",
    "SEN",
    "CIV",
]


def seed_relationship_types():
    with get_db() as db:
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
            db.rollback()
            print(f"Error seeding relationship types: {e}")
        finally:
            db.close()



def run_who_ingestion():
    print("Starting WHO GHO Insgestion Pipeline...")

    for indicator_code in WHO_INDICATOR_CODES_TO_INGEST:
        print(f"Processing indicator:" {indicator_code})

        #--- Step 1: Extract data ---
        print(f"Extracting raw data:" + indicator_code +"...")
        raw_who_data = []
        try:
            raw_who_data = extract_who_data(indicator_code, AFRICAN_COUNTRY_CODES_TO_INGEST)
            print(f"Extracted {len(raw_who_data)} rows for {indicator_code}.")
            if len(raw_who_data) == 0:
                print(f"No data extracted fpr {indicator_code}, skipping transformation and load.")
                continue
        except Exception as e:
            print(f"Error during extraction for {indicator_code}:" {e})
            continue
if __name__ == "__main__":
    seed_relationship_types()
