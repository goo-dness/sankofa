# run_epistemic_test.py
from sqlalchemy import text
from app.database import get_db
from computation.epistemic import resolve_epistemic_state

with get_db() as db:

    print("=== TEST 1: KNOWN ===")
    # Real malaria "treats" data should exist from ChEMBL ingestion.
    known_results = db.execute(
        text("""
            SELECT er.confidence, er.evidence_count
            FROM entity_relations er
            JOIN relationship_types rt ON er.relationship_id = rt.id
            JOIN entities d ON er.to_entity_id = d.id
            WHERE rt.name = 'treats'
              AND lower(trim(d.name)) = 'malaria'
            """)
    ).mappings().all()

    result1 = resolve_epistemic_state(
        db=db,
        query_results=[dict(row) for row in known_results],
        disease_name="malaria",
        relationship_type="treats",
    )
    print(result1)

    print("\n=== TEST 2: KNOWABLY_ABSENT ===")
    # Pick something WHO ingested (measures/prevalent_in) but check a
    # relationship_type it never touches for that disease, so
    # query_results comes back empty but coverage exists.
    result2 = resolve_epistemic_state(
        db=db,
        query_results=[],
        disease_name="malaria",
        relationship_type="measures",
    )
    print(result2)

    print("\n=== TEST 3: UNCHARTED ===")
    # traditionally_treats has zero data anywhere per CONTEXT.md §7.
    result3 = resolve_epistemic_state(
        db=db,
        query_results=[],
        disease_name="malaria",
        relationship_type="traditionally_treats",
    )
    print(result3)
