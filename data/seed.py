import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, get_db
from data.relationship_types import relationship_types_data
from ingestions.openalex import DISEASE_VOCABULARY, run_openalex_ingestion
from ingestions.pubmed import run_pubmed_ingestion
from ingestions.who import extract_who_data, load_to_database, transform_to_entities, INDICATOR_MAP
from models.relations_type import RelationshipTypes
from models.coverage import IngestionCoverage
from ingestions.chembl import run_chembl_ingestion, MESH_DISEASE_MAP
Base.metadata.create_all(bind=engine)


def record_coverage(db, domain: str, disease_name: str, source_name: str, relationship_type: str):
    normalized = disease_name.strip().lower()
    existing = (
        db.query(IngestionCoverage)
        .filter_by(disease_name=normalized, source_name=source_name, relationship_type=relationship_type)
        .first()
    )
    if existing:
        existing.last_ingested_at = datetime.now(timezone.utc)
    else:
        db.add(
            IngestionCoverage(
                domain=domain, disease_name=normalized, source_name=source_name, relationship_type=relationship_type
            )
        )
    db.commit()
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
            raw_who_data, extract_succeeded = extract_who_data(
                indicator_code, AFRICAN_COUNTRY_CODES_TO_INGEST
            )
            print(f"Extracted {len(raw_who_data)} rows for {indicator_code}.")
            if len(raw_who_data) == 0:
                disease_name = INDICATOR_MAP.get(indicator_code, indicator_code)
                if extract_succeeded:
                    print(
                    f" No data extracted for {indicator_code}--- extraction completed, no data.Skipping load."
                    )
                    with get_db() as db_session:
                        for rel_type in ("measures", "prevalent_in"):
                            record_coverage(db_session, "epidemiology", disease_name, "WHO GHO", rel_type)
                else:
                    print(f"No data extracted for {indicator_code} -- extraction FAILED, coverage not recorded.")
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
                disease_name = INDICATOR_MAP.get(indicator_code, indicator_code)
                touched_relationship_types = set(
                    r["relationship_name"] for r in transformed_relationships
                )
                for rel_type in touched_relationship_types:
                    record_coverage(db_session, "epidemiology", disease_name, "WHO GHO", rel_type)
            except Exception as e:
                print(f"  Error during database load for {indicator_code}: {e}")
    print("WHO GHO ingestion pipeline finished.")


def run_openalex():
    print("Starting OpenAlex ingestion pipeline...")
    for disease_name in DISEASE_VOCABULARY:
        extract_succeeded, touched_relationship_types = run_openalex_ingestion(disease_name)
        if extract_succeeded:
            with get_db() as db_session:
                for rel_type in touched_relationship_types:
                    record_coverage(db_session, "healthcare", disease_name, "OpenAlex", rel_type)
        else:
            print(f"Skipping coverage for {disease_name} -- OpenAlex extraction did not succeeded")
    print("OpenAlex ingestion pipeline finished.")


def run_pubmed():
    print("Starting PubMed ingestion pipeline...")
    for disease_name in DISEASE_VOCABULARY:
        extract_succeeded, touched_relationship_types = run_pubmed_ingestion(disease_name)
        if extract_succeeded:
            with get_db() as db_session:
                for rel_type in touched_relationship_types:
                    record_coverage(db_session, "healthcare", disease_name, "PubMed", rel_type)
        else:
            print(f"Skipping coverage for {disease_name} -- PubMed did not record the extraction")
    print("PubMed ingestion pipeline finished.")

def run_chembl():
    print("Starting ChEMBL ingestion pipeline...")
    for disease_name in MESH_DISEASE_MAP:
        extract_succeeded, touched_relationship_types = run_chembl_ingestion(disease_name)
        if extract_succeeded:
            with get_db() as db_session:
                for rel_type in touched_relationship_types:
                    record_coverage(db_session, "healthcare", disease_name, "ChEMBL", rel_type)
        else:
            print(f"SKipping coverage for {disease_name}-- no data reocrded")
        print("ChEMBL ingestion complete.")

if __name__ == "__main__":
    seed_relationship_types()
    run_who_ingestion()
    run_openalex()
    run_pubmed()
    run_chembl()
