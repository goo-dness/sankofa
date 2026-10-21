"""Run one real OpenAlex malaria ingestion and audit its coverage.

Run from the repository root:
    venv/bin/python tests/verify_openalex_malaria_coverage.py
"""

from sqlalchemy import text

import data.seed as seed
from app.database import get_db


def run_one_disease_ingestion():
    seed.DISEASE_VOCABULARY = ["malaria"]
    seed.run_openalex()


def verify_malaria_coverage_has_edges():
    with get_db() as db:
        coverage_rows = db.execute(
            text(
                """
                SELECT relationship_type, last_ingested_at
                FROM ingestion_coverage
                WHERE disease_name = 'malaria'
                  AND source_name = 'OpenAlex'
                ORDER BY relationship_type
                """
            )
        ).all()

        assert coverage_rows, "No OpenAlex malaria coverage was recorded"

        for relationship_type, timestamp in coverage_rows:
            edge_count = db.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM entity_relations er
                    JOIN relationship_types rt
                      ON rt.id = er.relationship_id
                    JOIN entities source_entity
                      ON source_entity.id = er.from_entity_id
                    JOIN entities target_entity
                      ON target_entity.id = er.to_entity_id
                    WHERE rt.name = :relationship_type
                      AND (
                          LOWER(source_entity.name) = 'malaria'
                          OR LOWER(target_entity.name) = 'malaria'
                      )
                    """
                ),
                {"relationship_type": relationship_type},
            ).scalar_one()

            print(
                f"{relationship_type}: {edge_count} matching edge(s), "
                f"coverage updated {timestamp}"
            )

            assert edge_count > 0, (
                "Coverage exists without a matching malaria edge: "
                f"{relationship_type}"
            )

    print("PASS: committed OpenAlex malaria data has matching coverage")


if __name__ == "__main__":
    run_one_disease_ingestion()
    verify_malaria_coverage_has_edges()
