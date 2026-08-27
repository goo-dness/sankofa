from enum import Enum
from sqlalchemy import text
from sqlalchemy.orm import Session
from computation.weighing import aggregate_confidence, aggregate_evidence

class EpistemicState(str, Enum):
    KNOWN = "Known"
    KNOWABLY_ABSENT = "Knowably absent"
    UNCHARTED = "Uncharted"

def has_coverage(db: Session, disease_name: str, relationship_type: str) -> list[str]:
    """
    Checks ingestion_coverage directly to see which sources (if any) have already checked this disease for this specific relationship type.
    Returns a list of source names (e.g. ["WHO GHO", "OpenAlex"]), r an empty list if nothing has ever checked this combination.
    """
    normalized_name = disease_name.strip().lower()

    rows = db.execute(text("""
        SELECT DISTINCT source_name
        FROM ingestion_coverage
        WHERE disease_name = :disease_name
            AND relationship_type = :relationship_type
        """), {"disease_name": normalized_name, "relationship_type": relationship_type}).mappings().all()
    return [row["source_name"] for row in rows]

def resolve_epistemic_state(
    db: Session,
    query_results: list[dict],
    disease_name: str,
    relationship_type: str,
) -> dict:
    """
    Classifies a query result into one of three epistemic states:
        1. KNOWN -- relationship exists, backed by >= 1 source.
        2. KNOWABLY_ABSENT -- this disease/relationship_type combo was genuinely checked by at least one source, nothing was found.
        3. UNCHARTED -- no osurce has ever checked this combo. A coverage gap, not a negative finding.
    """
    if query_results:
        return {
            "state": EpistemicState.KNOWN,
            "data": query_results,
            "confidence": aggregate_confidence(query_results),
            "evidence_count": aggregate_evidence(query_results),
        }

    sources_checked = has_coverage(db, disease_name, relationship_type)

    if sources_checked:
        return{
            "state": EpistemicState.KNOWABLY_ABSENT,
            "data": [],
            "message": (
                f"No established '{relationship_type}' relationship found "
                f"for '{disease_name}'. Sources checked: {', '.join(sources_checked)}"
            ),
        }

    return {
        "state": EpistemicState.UNCHARTED,
        "data": [],
        "message": (
            f"'{disease_name}' has not been ingested for '{relationship_type}' yet. "
            f"This is a coverage gap, not a negative finding."
        ),
    }
