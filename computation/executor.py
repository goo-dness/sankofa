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
from computation.epistemic import resolve_epistemic_state

CITATIONS_QUERY = text("""
    SELECT
        rs.relationshid_id,
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


def execute_single_hop(db: Session, source_name: str, relationship_type: str) -> dict:
    rows = db.execute(SINGLE_HOP_QUERY, {
        "source_name": source_name,
        "relationship_type": relationship_type,
    }).mappings().all()
    results = [dict(r) for r in rows]

    relationship_ids = [r["relationship_id"] for r in results]
    citations = fetch_citations(db, relationship_ids)

    return {
        "epistemic_state": resolve_epistemic_state(results),
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
        "epistemic_state": resolve_epistemic_state(results),
        "query_results": results,
        "citations": citations,
        "contradictions": detect_contradictions(results),
        "chain_weight": weigh_chain(results) if results else None,
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
        "epistemic_state": resolve_epistemic_state(results),
        "query_results": results,
        "citations": citations,
        "contradictions": detect_contradictions(results),
        "chain_weight": weigh_chain(results) if results else None,
    }

def execute_neighborhood(db: Session, entity_id: int, depth: int = 1,) -> dict:
    rows = db.execute(NEIGHBORHOOD_QUERY, {
        "entity_id": entity_id,
        "max_depth": depth,
    }).mappings().all()

    results = [dict(r) for r in rows]

    return {
        "entity_id": entity_id,
        "connections": results,
        "total_connections": len(results),
    }

def execute_path_query(db: Session, start_entity_id: int, end_entity_id: int, max_depth: int=3,) -> dict:
    rows = db.execute(PATH_QUERY, {
        "start_entity_id": start_entity_id,
        "end_entity_id": end_entity_id,
        "max_depth": max_depth,
    }).mappings().all()

    results = [dict(r) for r in rows]

    return {
        "path": results[0] if results else None,
        "found": len(results) > 0,
    }
