from collections import defaultdict
from sqlalchemy import text
from sqlalchemy.orm import Session
from computation.queries import (
    SINGLE_HOP_QUERY,
    TWO_HOP_FORWARD_QUERY,
    TWO_HOP_BACKWARD_QUERY,
    NEIGHBORHOOD_QUERY,
    PATH_QUERY
)
from computation.weighing import aggregate_confidence, aggregate_evidence, weigh_chain
from computation.contradictions import detect_contradictions
from computation.epistemic import resolve_epistemic_state, EpistemicState

CITATIONS_QUERY = text("""
    SELECT
        rs.relationship_id,
        rs.source_name,
        rs.source_url,
        rs.source_author,
        rs.source_title,
        rs.confidence
    FROM relationship_sources rs
    WHERE rs.relationship_id = ANY(:relationship_ids)
    """)

def fetch_citations(db: Session, relationship_ids: list[int]) -> dict[int, list[dict]]:
    if not relationship_ids:
        return {}
    rows = db.execute(CITATIONS_QUERY, {"relationship_ids": relationship_ids}).mappings().all()
    citations: dict[int, list[dict]] = {}

    for r in rows:
        rid = r["relationship_id"]
        citations.setdefault(rid, []).append(dict(r))
    return citations

def group_results_by_fact(results: list[dict], is_neighborhood: bool) -> dict:
    # the same fact = same (from_entity_id, to_entity_id) pair
    # for two_hop queries, or same connected_entity_id for neighborhood queries
    grouped = defaultdict(list)
    for row in results:
        if is_neighborhood:
            fact_key = row["connected_entity_id"]
        else:
            fact_key = row["from_entity_id"], row["to_entity_id"]
        grouped[fact_key].append(row)
    return grouped

def compute_chain_weights(results: list[dict], is_neighborhood: bool) -> dict:
    # Returns one weigh_chain() result per distinct fact, not one
    # global blended result for the whole query
    grouped = group_results_by_fact(results, is_neighborhood)

    chain_weights = {}
    for fact_key, group_rows in grouped.items():
        chain_weights[fact_key] = weigh_chain(group_rows)
    return chain_weights


def execute_single_hop(db: Session, source_name: str, relationship_type: str) -> dict:
    rows = db.execute(SINGLE_HOP_QUERY, {
        "source_name": source_name,
        "relationship_type": relationship_type,
    }).mappings().all()
    results = [dict(r) for r in rows]

    relationship_ids = [r["relationship_id"] for r in results]
    citations = fetch_citations(db, relationship_ids)

    return {
        "epistemic_state": resolve_epistemic_state(db, results, source_name, relationship_type),
        "query_results": results,
        "citations": citations,
        "contradictions": [],
        "chain_weight": None,
    }

def execute_two_hop_forward(db: Session, source_name: str, first_relationship: str, second_relationship: str, max_depth: int = 2, ) -> dict:
    rows = db.execute(TWO_HOP_FORWARD_QUERY, {
        "source_name": source_name,
        "first_relationship": first_relationship,
        "second_relationship": second_relationship,
        "max_depth": max_depth,
    }).mappings().all()

    results = [dict(r) for r in rows]

    all_ids = set()
    for r in results:
        all_ids.update(r["relationship_ids"])
    citations = fetch_citations(db, list(all_ids))

    return {
        "epistemic_state": resolve_epistemic_state(results),  # ITEM 4 — not fixed yet, deliberately left as-is
        "query_results": results,
        "citations": citations,
        "contradictions": detect_contradictions(results),
        "chain_weight": compute_chain_weights(results, is_neighborhood=False) if results else None,
    }

def execute_two_hop_backward(db: Session, target_name: str, first_relationship: str, second_relationship: str, max_depth: int= 2,) -> dict:
    rows = db.execute(TWO_HOP_BACKWARD_QUERY, {
        "target_name": target_name,
        "first_relationship": first_relationship,
        "second_relationship": second_relationship,
        "max_depth": max_depth,
    }).mappings().all()

    results = [dict(r) for r in rows]

    all_ids = set()
    for r in results:
        all_ids.update(r["relationship_ids"])
    citations = fetch_citations(db, list(all_ids))

    return {
        "epistemic_state": resolve_epistemic_state(results),  # ITEM 4 — not fixed yet, deliberately left as-is
        "query_results": results,
        "citations": citations,
        "contradictions": detect_contradictions(results),
        "chain_weight": compute_chain_weights(results, is_neighborhood=False) if results else None,
    }

def execute_neighborhood(db: Session, entity_id: int, depth: int = 1,) -> dict:
    rows = db.execute(NEIGHBORHOOD_QUERY, {
        "entity_id": entity_id,
        "max_depth": depth,
    }).mappings().all()

    results = [dict(r) for r in rows]

    # Reconstruct from_entity_id/to_entity_id per row using direction +
    # the newly-exposed connected_entity_id, so detect_contradictions
    # can operate on entity pairs the same way two-hop results do.
    for row in results:
        if row["direction"] == "outgoing":
            row["from_entity_id"] = entity_id
            row["to_entity_id"] = row["connected_entity_id"]
        else:  # "incoming"
            row["from_entity_id"] = row["connected_entity_id"]
            row["to_entity_id"] = entity_id

    all_ids = set()
    for r in results:
        all_ids.update(r["relationship_ids"])
    citations = fetch_citations(db, list(all_ids))

    return {
        "epistemic_state": resolve_epistemic_state(results),  # ITEM 4 — not fixed yet, deliberately left as-is
        "query_results": results,
        "citations": citations,
        "contradictions": detect_contradictions(results),
        "chain_weight": compute_chain_weights(results, is_neighborhood=True) if results else None,
    }

def execute_path_query(db: Session, start_entity_id: int, end_entity_id: int, max_depth: int=3,) -> dict:
    rows = db.execute(PATH_QUERY, {
        "start_entity_id": start_entity_id,
        "end_entity_id": end_entity_id,
        "max_depth": max_depth,
    }).mappings().all()

    results = [dict(r) for r in rows]
    found = len(results) > 0

    # contradictions/citations/chain_weight are intentionally empty:
    # PATH_QUERY returns one collapsed best path, not competing edges
    # per entity pair, so contradiction detection isn't meaningful
    # here yet without restructuring into per-hop rows (deferred).
    # PATH_QUERY also doesn't expose confidence/evidence_count per
    # row, so aggregate_confidence/weigh_chain can't run on it as-is.
    epistemic_state = {
        "state": EpistemicState.KNOWN if found else EpistemicState.KNOWABLY_ABSENT,
        "data": results,
    }
    if not found:
        epistemic_state["message"] = "No path found between these entities."

    return {
        "epistemic_state": epistemic_state,
        "query_results": results,
        "citations": {},
        "contradictions": [],
        "chain_weight": None,
    }
