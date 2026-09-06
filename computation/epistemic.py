from enum import Enum
from sqlalchemy import text
from sqlalchemy.orm import Session
from computation.weighing import aggregate_confidence, aggregate_evidence
from computation.queries import SINGLE_HOP_QUERY, SINGLE_HOP_BACKWARD_QUERY

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

def resolve_chain_epistemic_state_forward(db, query_results, source_name, first_relationship, second_relationship):
    if query_results:
        return resolve_epistemic_state(db, query_results, source_name, first_relationship)

    hop1_sources = has_coverage(db, source_name, first_relationship)
    if not hop1_sources:
        return {"state": EpistemicState.UNCHARTED, "data": [], "message": f"'{source_name}' not checked for '{first_relationship}' yet -- coverage gap at hop 1."}

    hop1_rows = db.execute(SINGLE_HOP_QUERY, {"source_name": source_name, "relationship_type": first_relationship}).mappings().all()

    if not hop1_rows:
        return {"state": EpistemicState.KNOWABLY_ABSENT, "data": [], "message": f"No '{first_relationship}' relationship found for '{source_name}'. Sources checked: {hop1_sources}."}

    for row in hop1_rows:
        intermediate_name = row["to_name"]
        hop2_sources = has_coverage(db, intermediate_name, second_relationship)

        if not hop2_sources:
            return {"state": EpistemicState.UNCHARTED, "data": [], "message": f"Some intermediates from '{first_relationship}' not checked for '{second_relationship}' yet -- coverage gap for hop 2."}

    return {"state": EpistemicState.KNOWABLY_ABSENT, "data": [], "message": f"No two-hop chain found via '{first_relationship}' -> '{second_relationship}' from '{source_name}'. All intermediates checked."}

def resolve_chain_epistemic_state_backward(db, query_results, target_name, first_relationship, second_relationship):
    if query_results:
        return resolve_epistemic_state(db, query_results, target_name, first_relationship)

    hop1_sources = has_coverage(db, target_name, first_relationship)
    if not hop1_sources:
        return {"state": EpistemicState.UNCHARTED, "data": [], "message": f"'{target_name}' not checked for '{first_relationship}' yet -- coverage gap at hop 1."}

    hop1_rows = db.execute(SINGLE_HOP_BACKWARD_QUERY, {"target_name": target_name, "relationship_type": first_relationship}).mappings().all()

    if not hop1_rows:
        return {"state": EpistemicState.KNOWABLY_ABSENT, "data": [], "message": f"No '{first_relationship}' found leading to '{target_name}'. Sources checked: {hop1_sources}."}

    for row in hop1_rows:
        intermediate_name = row["from_name"]
        hop2_sources = has_coverage(db, intermediate_name, second_relationship)

        if not hop2_sources:
            return {"state": EpistemicState.UNCHARTED, "data": [], "message": f"Some intermediates not checked for '{second_relationship}' yet -- coverage gap at hop 2."}

    return {"state": EpistemicState.KNOWABLY_ABSENT, "data": [], "message": f"No two-hop chain found via '{first_relationship}' <- '{second_relationship}' into '{target_name}'. All intermediates checked."}
