"""Verify that a failed load cannot cause coverage to be recorded.

Run from the repository root:
    venv/bin/python tests/verify_coverage_failure.py
"""

from app.database import SessionLocal
from ingestions.openalex import load as openalex_load


def verify_load_reports_rollback():
    """Cause a safe validation failure after the DB connection succeeds."""
    db_session = SessionLocal()

    try:
        # Missing "name" causes load() to enter its exception/rollback path
        # before an entity can be inserted.
        load_succeeded = openalex_load(
            [{"domain": "healthcare"}],
            [],
            [],
            db_session,
        )
    finally:
        db_session.close()

    assert load_succeeded is False, (
        f"Expected False after rollback, got {load_succeeded!r}"
    )
    print("PASS: failed OpenAlex load returns False")


def verify_batch_runners_skip_coverage():
    """Exercise the batch condition without making an ingestion request."""
    import data.seed as seed

    coverage_calls = []

    seed.DISEASE_VOCABULARY = ["coverage-gate-control"]
    seed.record_coverage = lambda *args, **kwargs: coverage_calls.append(
        (args, kwargs)
    )

    seed.run_openalex_ingestion = lambda disease_name: (
        True,
        False,
        {"associated_with"},
    )
    seed.run_openalex()

    assert coverage_calls == [], (
        "OpenAlex recorded coverage despite load_succeeded being False"
    )

    seed.run_pubmed_ingestion = lambda disease_name: (
        True,
        False,
        {"associated_with"},
    )
    seed.run_pubmed()

    assert coverage_calls == [], (
        "PubMed recorded coverage despite load_succeeded being False"
    )
    print("PASS: batch runners skip coverage after failed loads")


if __name__ == "__main__":
    verify_load_reports_rollback()
    verify_batch_runners_skip_coverage()
