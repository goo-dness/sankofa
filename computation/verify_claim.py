from sqlalchemy.orm.session import Session

from computation.epistemic import EpistemicState
from computation.executor import execute_constraint_query


def verify_claim(
    db: Session,
    source_name: str,
    target_name: str,
    relationship_type: str,
    max_depth: int = 3,
) -> dict:
    # ----- extra check: claim triple must be present ---
    if not source_name:
        return {
            "epistemic_state": {
                "state": EpistemicState.UNCHARTED,
                "message": "Source entity name is required",
            },
            "query_results": [],
            "citations": {},
            "contradictions": [],
            "chain_weight": None,
        }

    if not target_name:
        return {
            "epistemic_state": {
                "state": EpistemicState.UNCHARTED,
                "message": "Target entity required",
            },
            "query_results": [],
            "citations": {},
            "contradictions": [],
            "chain_weight": None,
        }

    if not relationship_type:
        return {
            "epistemic_state": {
                "state": EpistemicState.UNCHARTED,
                "message": "Relationship type required",
            },
            "query_results": [],
            "citations": {},
            "contradictions": [],
            "chain_weight": None,
        }

    # --- verification mode: delegate to constrained executor ---
    # Relationship type is assume already resolved by Litsi
    # Direction is assumed already normalized
    # No path re-search, no coverage logic, no scoring here
    result = execute_constraint_query(
        db, source_name, target_name, relationship_type, max_depth
    )

    return result
