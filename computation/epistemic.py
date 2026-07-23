from enum import Enum
from computation.weighing import aggregate_confidence, aggregate_evidence
class EpistemicState(str, Enum):
    KNOWN = "Known"
    KNOWABLY_ABSENT = "Knowably absent"
    UNCHARTED = "Uncharted"

def resolve_epistemic_state(query_results: list[dict], coverage_registry: dict[str, list[str]] | None = None, disease_name: str | None = None, ) -> dict:
    f"""Classify query results into one of three epistemic states
    1. Known --- relationship exists, backed by >= 1 source
    2. Knowably absent --- domain was ingested, nothing found
    3. Uncharted --- domain hasn`t been ingested yet

    coverage_registry: {disease_name: [source_names_ingested]}
    Only needed for full three-state support; can be None initially.
    """
    if query_results:
        return{
            "state": EpistemicState.KNOWN,
            "data": query_results,
            "confidence": aggregate_confidence(query_results),
            "evidence_count": aggregate_evidence(query_results)
        }

    if coverage_registry is None or disease_name is None:
        return {
            "state": EpistemicState.KNOWABLY_ABSENT,
            "data": [],
            "message": "No established relationship found.",
        }

    if disease_name in coverage_registry:
        return{
            "state": EpistemicState.KNOWABLY_ABSENT,
            "data": [],
            "message": f"No established relationship found. "
                        f"Sources checked: {', '.join(coverage_registry[disease_name])}",
        }

    return{
        "state": EpistemicState.UNCHARTED,
        "data": [],
        "message": f" '{disease_name}' has not been ingested yet. "
                   f"This is a coverage gap, not a negative finding.",
    }
