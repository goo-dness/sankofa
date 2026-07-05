import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, get_db
from data.relationship_types import relationship_types_data
from ingestions.openalex import DISEASE_VOCABULARY, run_openalex_ingestion
from ingestions.pubmed import run_pubmed_ingestion
from ingestions.who import extract_who_data, load_to_database, transform_to_entities
from models.relations_type import RelationshipTypes

Base.metadata.create_all(bind=engine)
# Define insertion parameters
WHO_INDICATOR_CODES_TO_INGEST = [
    "MALARIA_EST_INCIDENCE",
    "SDGHIV",
    "MDG_0000000020",
    "CM_01",  # Child mortality
    "MDG_0000000026",  # Maternal mortality rate
    # "CHOLERA_TOTAL",
    "MDG_0000000017",
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
            print("Relationship types seeded successfully.")
        except Exception as e:
            db.rollback()
            print(f" Error seeding relationship types: {e}")


def run_who_ingestion():
    print("Starting WHO GHO Ingestion Pipeline...")

    for indicator_code in WHO_INDICATOR_CODES_TO_INGEST:
        print(f" Processing indicator: {indicator_code}")

        # --- Step 1: Extract data ---
        print(f" Extracting raw data: {indicator_code} ...")
        raw_who_data = []
        try:
            raw_who_data = extract_who_data(
                indicator_code, AFRICAN_COUNTRY_CODES_TO_INGEST
            )
            print(f"Extracted {len(raw_who_data)} rows for {indicator_code}.")
            if len(raw_who_data) == 0:
                print(
                    f" No data extracted for {indicator_code}, skipping transformation and load."
                )
                continue
        except Exception as e:
            print(f" Error during extraction for {indicator_code}:", {e})
            continue

        # --- Step 2: Transform data ---
        print(
            f" Transforming data for {indicator_code} into entities and relationships..."
        )
        transformed_entities = []
        transformed_relationships = []
        try:
            transformed_entities, transformed_relationships, transformed_sources = (
                transform_to_entities(raw_who_data, indicator_code)
            )
            print(
                f"Transformed into {len(transformed_entities)} entities and {len(transformed_relationships)} relationships"
            )
        except Exception as e:
            print(f"Error during transformation for {indicator_code}:", {e})
            continue

        # ---Step 3: Load to database---
        print(f"Loading transformed data for {indicator_code} to the database..")
        with get_db() as db_session:
            try:
                # This is the line to check
                load_to_database(
                    db_session,
                    transformed_entities,
                    transformed_relationships,
                    transformed_sources,
                )
                print(f"  Successfully loaded data for {indicator_code} to database.")
            except Exception as e:
                print(f"  Error during database load for {indicator_code}: {e}")
    print("WHO GHO ingestion pipeline finished.")


def run_openalex():
    print("Starting OpenAlex ingestion pipeline...")
    for disease_name in DISEASE_VOCABULARY:
        run_openalex_ingestion(disease_name)
    print("OpenAlex ingestion pipeline finished.")


def run_pubmed():
    print("Starting PubMed ingestion pipeline...")
    for disease_name in DISEASE_VOCABULARY:
        run_pubmed_ingestion(disease_name)
    print("PubMed ingestion pipeline finished.")


if __name__ == "__main__":
    seed_relationship_types()
    run_who_ingestion()
    run_openalex()
    run_pubmed()
