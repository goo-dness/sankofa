# Computational Symbolic Engine — Architecture

**Date:** July 2026
**Decision:** Postgres recursive CTEs + plain Python (no logic-programming library)
**Status:** In progress

---

## 1. Overview

The Computational Symbolic Engine is Sankofa's symbolic reasoning layer. It answers multi-hop queries over the knowledge graph by traversing `entity_relations` edges using Postgres `WITH RECURSIVE` CTEs, then applying Python functions for evidence weighing, contradiction detection, and three-state epistemic resolution.

**What the engine does NOT do:** open-ended reasoning, unification-based backtracking search, or rule inference. The query catalog is bounded and fixed-shape — single-hop lookups, 2-3 hop chains, evidence aggregation, contradiction checks. This is deliberate: bounded traversal is predictable and suitable for live query-serving.

---

## 2. Graph Schema Recap

```
entities (nodes)
├── id: INT PK
├── name: VARCHAR NOT NULL
├── domain: VARCHAR (e.g. "healthcare", "epidemiology", "pharmacology")
├── entity_type: VARCHAR (e.g. "Clinical", "Molecule", "Country")
├── confidence: INT (1-3)
├── evidence_count: INT (default 1)
└── ...

entity_relations (directed edges)
├── id: INT PK
├── from_entity_id: FK → entities.id
├── to_entity_id: FK → entities.id
├── relationship_id: FK → relationship_types.id
├── confidence: INT (1-3)
├── evidence_count: INT (default 1)
├── context: VARCHAR
└── ...

relationship_types (edge labels)
├── id: INT PK
├── name: VARCHAR UNIQUE (e.g. "treats", "causes", "prevalent_in")
├── label: VARCHAR (human-readable)
├── domain: VARCHAR (e.g. "pathology", "pharmacology", "ethnomedicine")
└── ...

relationship_sources (per-edge provenance)
├── id: INT PK
├── relationship_id: FK → entity_relations.id
├── source_name: VARCHAR
├── source_url: VARCHAR
├── confidence: INT (this source's own rating)
└── ...
```

**Key properties:**
- Graph is directed (from → to), but the engine treats it as undirectional for neighborhood queries
- Each edge carries its own confidence and evidence_count
- 62 relationship types seeded across 9 domains

---

## 3. CTE Query Patterns

### 3.1 Single-Hop Query

Use case: "What treats malaria?"

```sql
SELECT
    e_from.id AS from_id,
    e_from.name AS from_name,
    e_to.id AS to_id,
    e_to.name AS to_name,
    rt.name AS relationship_type,
    er.confidence,
    er.evidence_count,
    er.context
FROM entity_relations er
JOIN entities e_from ON er.from_entity_id = e_from.id
JOIN entities e_to ON er.to_entity_id = e_to.id
JOIN relationship_types rt ON er.relationship_id = rt.id
WHERE e_from.name = :source_name
  AND rt.name = :relationship_type;
```

### 3.2 Fixed-Depth Recursive CTE (2-hop)

Use case: "What drugs target pathways involved in diseases prevalent in Nigeria?"

```sql
WITH RECURSIVE traversal AS (
    -- Anchor: find diseases prevalent in Nigeria
    SELECT
        er.from_entity_id,
        er.to_entity_id,
        er.relationship_id,
        er.confidence,
        er.evidence_count,
        1 AS depth,
        ARRAY[er.from_entity_id, er.to_entity_id] AS path
    FROM entity_relations er
    JOIN relationship_types rt ON er.relationship_id = rt.id
    JOIN entities e ON er.to_entity_id = e.id
    WHERE e.name = :target_name
      AND rt.name = :first_hop_relationship

    UNION ALL

    -- Recursive: follow second hop
    SELECT
        er.from_entity_id,
        er.to_entity_id,
        er.relationship_id,
        er.confidence,
        er.evidence_count,
        t.depth + 1,
        t.path || er.to_entity_id
    FROM entity_relations er
    JOIN traversal t ON er.from_entity_id = t.to_entity_id
    JOIN relationship_types rt ON er.relationship_id = rt.id
    WHERE rt.name = :second_hop_relationship
      AND t.depth < :max_depth
      AND er.to_entity_id != ALL(t.path)  -- cycle prevention
)
SELECT
    e1.name AS from_name,
    e2.name AS to_name,
    rt.name AS relationship_type,
    t.confidence,
    t.evidence_count,
    t.depth
FROM traversal t
JOIN entities e1 ON t.from_entity_id = e1.id
JOIN entities e2 ON t.to_entity_id = e2.id
JOIN relationship_types rt ON t.relationship_id = rt.id;
```

**Cycle prevention:** The `path` array tracks visited node IDs. Each new hop checks `er.to_entity_id != ALL(t.path)` to prevent infinite loops on cyclic graphs.

### 3.3 Bidirectional Neighborhood

Use case: "What is connected to malaria?" (any direction)

```sql
SELECT DISTINCT
    e1.id AS entity_id,
    e1.name AS entity_name,
    rt.name AS relationship_type,
    CASE
        WHEN er.from_entity_id = :entity_id THEN 'outgoing'
        ELSE 'incoming'
    END AS direction,
    er.confidence,
    er.evidence_count
FROM entity_relations er
JOIN relationship_types rt ON er.relationship_id = rt.id
JOIN entities e1 ON (
    CASE
        WHEN er.from_entity_id = :entity_id THEN er.to_entity_id
        ELSE er.from_entity_id
    END = e1.id
)
WHERE er.from_entity_id = :entity_id
   OR er.to_entity_id = :entity_id;
```

### 3.4 Path Finding (shortest path between two entities)

Use case: "How is Drug X connected to Disease Y?"

```sql
WITH RECURSIVE path_search AS (
    SELECT
        er.from_entity_id,
        er.to_entity_id,
        er.relationship_id,
        1 AS depth,
        ARRAY[er.from_entity_id] AS visited,
        ARRAY[rt.name] AS relationship_path
    FROM entity_relations er
    JOIN relationship_types rt ON er.relationship_id = rt.id
    WHERE er.from_entity_id = :start_entity_id

    UNION ALL

    SELECT
        er.from_entity_id,
        er.to_entity_id,
        er.relationship_id,
        ps.depth + 1,
        ps.visited || er.from_entity_id,
        ps.relationship_path || rt.name
    FROM entity_relations er
    JOIN path_search ps ON er.from_entity_id = ps.to_entity_id
    JOIN relationship_types rt ON er.relationship_id = rt.id
    WHERE ps.depth < :max_depth
      AND er.to_entity_id != ALL(ps.visited)
      AND ps.to_entity_id != :end_entity_id  -- stop when target reached
)
SELECT
    e1.name AS from_name,
    e2.name AS to_name,
    ps.relationship_path,
    ps.depth
FROM path_search ps
JOIN entities e1 ON ps.from_entity_id = e1.id
JOIN entities e2 ON ps.to_entity_id = e2.id
WHERE ps.to_entity_id = :end_entity_id
ORDER BY ps.depth
LIMIT 1;
```

---

## 4. Python Layer

Operates on CTE query results. No ORM dependency — receives lists of dicts from raw SQL execution.

### 4.1 Evidence Weighing

```python
def aggregate_confidence(chain: list[dict]) -> int:
    """Return max confidence across a chain.

    Principle: one strong RCT (confidence=3) should outweigh
    ten weak case reports (confidence=1). Max, not average.
    """
    if not chain:
        return 0
    return max(r["confidence"] for r in chain)


def aggregate_evidence(chain: list[dict]) -> int:
    """Sum evidence_count across independent confirmations.

    Each new source that confirms a claim adds +1 to evidence_count.
    Summing across a chain gives total independent confirmations.
    """
    if not chain:
        return 0
    return sum(r["evidence_count"] for r in chain)


def weigh_chain(chain: list[dict]) -> dict:
    """Aggregate confidence and evidence for a traversal chain."""
    return {
        "confidence": aggregate_confidence(chain),
        "evidence_count": aggregate_evidence(chain),
        "hop_count": len(chain),
    }
```

### 4.2 Contradiction Detection

```python
from collections import defaultdict

# Known conflict pairs: relationship types that semantically contradict
# each other when applied to the same entity pair.
CONFLICT_PAIRS: set[tuple[str, str]] = {
    ("prevents", "causes"),
    ("treats", "contraindicated_with"),
    ("prevents", "risk_factor_for"),
    ("activates", "suppresses"),
    ("protective_against", "predisposes_to"),
    ("synergizes_with", "antagonizes"),
    ("inhibits", "activates"),
    ("inhibits", "produces"),
}


def detect_contradictions(results: list[dict]) -> list[dict]:
    """Flag entity pairs with conflicting relationship types.

    Example: "X treats Y" AND "X contraindicated_with Y" on the
    same (from_entity, to_entity) pair.
    """
    entity_pairs: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for r in results:
        key = (r["from_entity_id"], r["to_entity_id"])
        entity_pairs[key].append(r)

    contradictions = []
    for pair_key, relationships in entity_pairs.items():
        rel_types = {r["relationship_type"] for r in relationships}
        for conflict in CONFLICT_PAIRS:
            if conflict[0] in rel_types and conflict[1] in rel_types:
                contradictions.append({
                    "from_entity_id": pair_key[0],
                    "to_entity_id": pair_key[1],
                    "conflicting_types": list(conflict),
                    "relationships": [
                        r for r in relationships
                        if r["relationship_type"] in conflict
                    ],
                })

    return contradictions
```

### 4.3 Three-State Epistemic Resolution

```python
from enum import Enum


class EpistemicState(str, Enum):
    KNOWN = "Known"
    KNOWABLY_ABSENT = "Knowably absent"
    UNCHARTED = "Uncharted"


def resolve_epistemic_state(
    query_results: list[dict],
    coverage_registry: dict[str, list[str]] | None = None,
    disease_name: str | None = None,
) -> dict:
    """Classify query results into one of three epistemic states.

    1. Known — relationship exists, backed by ≥1 source
    2. Knowably absent — domain was ingested, nothing found
    3. Uncharted — domain hasn't been ingested yet

    coverage_registry: {disease_name: [source_names_ingested]}
    Only needed for full three-state support; can be None initially.
    """
    if query_results:
        return {
            "state": EpistemicState.KNOWN,
            "data": query_results,
            "confidence": aggregate_confidence(query_results),
            "evidence_count": aggregate_evidence(query_results),
        }

    # Without coverage registry, absence = "Knowably absent" by default
    # (all ingested diseases are in the graph)
    if coverage_registry is None or disease_name is None:
        return {
            "state": EpistemicState.KNOWABLY_ABSENT,
            "data": [],
            "message": "No established relationship found.",
        }

    if disease_name in coverage_registry:
        return {
            "state": EpistemicState.KNOWABLY_ABSENT,
            "data": [],
            "message": f"No established relationship found. "
                       f"Sources checked: {', '.join(coverage_registry[disease_name])}",
        }

    return {
        "state": EpistemicState.UNCHARTED,
        "data": [],
        "message": f"'{disease_name}' has not been ingested yet. "
                   f"This is a coverage gap, not a negative finding.",
    }
```

---

## 5. Query Executor

Bridges CTE SQL execution and Python logic. Uses raw SQL via SQLAlchemy's `execute()` (not ORM queries) for full CTE control.

```python
from sqlalchemy import text
from sqlalchemy.orm import Session


def execute_single_hop(
    db: Session,
    source_name: str,
    relationship_type: str,
) -> dict:
    """Single-hop query: what is connected to source via this relationship?"""
    sql = text("""
        SELECT
            e_from.id AS from_id,
            e_from.name AS from_name,
            e_to.id AS to_id,
            e_to.name AS to_name,
            rt.name AS relationship_type,
            er.confidence,
            er.evidence_count,
            er.context
        FROM entity_relations er
        JOIN entities e_from ON er.from_entity_id = e_from.id
        JOIN entities e_to ON er.to_entity_id = e_to.id
        JOIN relationship_types rt ON er.relationship_id = rt.id
        WHERE e_from.name = :source_name
          AND rt.name = :relationship_type
    """)

    rows = db.execute(sql, {
        "source_name": source_name,
        "relationship_type": relationship_type,
    }).mappings().all()

    return resolve_epistemic_state([dict(r) for r in rows])


def execute_two_hop(
    db: Session,
    source_name: str,
    first_relationship: str,
    second_relationship: str,
    max_depth: int = 2,
) -> dict:
    """Two-hop query: source -> first_relationship -> entity -> second_relationship -> target."""
    sql = text("""
        WITH RECURSIVE traversal AS (
            SELECT
                er.from_entity_id,
                er.to_entity_id,
                er.relationship_id,
                er.confidence,
                er.evidence_count,
                1 AS depth,
                ARRAY[er.from_entity_id, er.to_entity_id] AS path
            FROM entity_relations er
            JOIN relationship_types rt ON er.relationship_id = rt.id
            JOIN entities e ON er.from_entity_id = e.id
            WHERE e.name = :source_name
              AND rt.name = :first_relationship

            UNION ALL

            SELECT
                er.from_entity_id,
                er.to_entity_id,
                er.relationship_id,
                er.confidence,
                er.evidence_count,
                t.depth + 1,
                t.path || er.to_entity_id
            FROM entity_relations er
            JOIN traversal t ON er.from_entity_id = t.to_entity_id
            JOIN relationship_types rt ON er.relationship_id = rt.id
            WHERE rt.name = :second_relationship
              AND t.depth < :max_depth
              AND er.to_entity_id != ALL(t.path)
        )
        SELECT
            e1.name AS from_name,
            e2.name AS to_name,
            rt.name AS relationship_type,
            t.confidence,
            t.evidence_count,
            t.depth
        FROM traversal t
        JOIN entities e1 ON t.from_entity_id = e1.id
        JOIN entities e2 ON t.to_entity_id = e2.id
        JOIN relationship_types rt ON t.relationship_id = rt.id
    """)

    rows = db.execute(sql, {
        "source_name": source_name,
        "first_relationship": first_relationship,
        "second_relationship": second_relationship,
        "max_depth": max_depth,
    }).mappings().all()

    results = [dict(r) for r in rows]
    contradictions = detect_contradictions(results)

    return {
        "epistemic_state": resolve_epistemic_state(results),
        "contradictions": contradictions,
        "chain_weight": weigh_chain(results) if results else None,
    }


def execute_neighborhood(
    db: Session,
    entity_id: int,
    depth: int = 1,
) -> dict:
    """Bidirectional neighborhood: all entities connected to entity_id within depth hops."""
    sql = text("""
        WITH RECURSIVE neighborhood AS (
            SELECT DISTINCT ON (CASE WHEN er.from_entity_id = :eid THEN er.to_entity_id ELSE er.from_entity_id END)
                CASE WHEN er.from_entity_id = :eid THEN er.to_entity_id ELSE er.from_entity_id END AS connected_id,
                rt.name AS relationship_type,
                CASE WHEN er.from_entity_id = :eid THEN 'outgoing' ELSE 'incoming' END AS direction,
                er.confidence,
                er.evidence_count,
                1 AS depth
            FROM entity_relations er
            JOIN relationship_types rt ON er.relationship_id = rt.id
            WHERE er.from_entity_id = :eid OR er.to_entity_id = :eid

            UNION

            SELECT DISTINCT ON (CASE WHEN er.from_entity_id = n.connected_id THEN er.to_entity_id ELSE er.from_entity_id END)
                CASE WHEN er.from_entity_id = n.connected_id THEN er.to_entity_id ELSE er.from_entity_id END,
                rt.name,
                CASE WHEN er.from_entity_id = n.connected_id THEN 'outgoing' ELSE 'incoming' END,
                er.confidence,
                er.evidence_count,
                n.depth + 1
            FROM entity_relations er
            JOIN neighborhood n ON (
                er.from_entity_id = n.connected_id OR er.to_entity_id = n.connected_id
            )
            JOIN relationship_types rt ON er.relationship_id = rt.id
            WHERE n.depth < :depth
        )
        SELECT
            e.name AS entity_name,
            n.relationship_type,
            n.direction,
            n.confidence,
            n.evidence_count,
            n.depth
        FROM neighborhood n
        JOIN entities e ON n.connected_id = e.id
        ORDER BY n.depth, e.name
    """)

    rows = db.execute(sql, {"eid": entity_id, "depth": depth}).mappings().all()
    results = [dict(r) for r in rows]

    return {
        "entity_id": entity_id,
        "connections": results,
        "total_connected": len(results),
    }
```

---

## 6. API Endpoints

```python
# routers/engine.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db

router = APIRouter(prefix="/engine", tags=["Computational Symbolic Engine"])


@router.get("/query")
def query_single_hop(
    source: str = Query(..., description="Source entity name"),
    relationship: str = Query(..., description="Relationship type name"),
    db: Session = Depends(get_db),
):
    """Single-hop query: what is connected to source via this relationship?"""
    return execute_single_hop(db, source, relationship)


@router.get("/chain")
def query_two_hop(
    source: str = Query(..., description="Source entity name"),
    first_relationship: str = Query(..., alias="first", description="First hop relationship type"),
    second_relationship: str = Query(..., alias="second", description="Second hop relationship type"),
    max_hops: int = Query(2, ge=1, le=3, description="Maximum traversal depth"),
    db: Session = Depends(get_db),
):
    """Multi-hop query: follow a chain of relationships from source."""
    return execute_two_hop(db, source, first_relationship, second_relationship, max_hops)


@router.get("/neighborhood")
def get_neighborhood(
    entity_id: int = Query(..., alias="entity", description="Entity ID"),
    depth: int = Query(1, ge=1, le=3, description="Traversal depth"),
    db: Session = Depends(get_db),
):
    """All entities connected to entity_id within depth hops (bidirectional)."""
    return execute_neighborhood(db, entity_id, depth)


@router.get("/path")
def find_path(
    from_entity: str = Query(..., alias="from", description="Start entity name"),
    to_entity: str = Query(..., alias="to", description="End entity name"),
    max_hops: int = Query(3, ge=1, le=3, description="Maximum path length"),
    db: Session = Depends(get_db),
):
    """Find shortest path between two entities."""
    return execute_path_finder(db, from_entity, to_entity, max_hops)
```

---

## 7. File Structure

```
sankofa/
├── computation/
│   ├── __init__.py          # Package exports
│   ├── queries.py           # CTE SQL queries (text() strings)
│   ├── executor.py          # execute_single_hop, execute_two_hop, etc.
│   ├── weighing.py          # aggregate_confidence, aggregate_evidence, weigh_chain
│   ├── contradictions.py    # detect_contradictions, CONFLICT_PAIRS
│   └── epistemic.py         # resolve_epistemic_state, EpistemicState enum
└── routers/
    └── engine.py            # FastAPI router endpoints
```

---

## 8. Implementation Order

| Phase | What | Depends on |
|-------|------|------------|
| 1 | Single-hop CTE queries + Python evidence-weighing | Nothing |
| 2 | Fixed-depth recursive CTEs (2-3 hop) | Phase 1 |
| 3 | Contradiction detection logic | Phase 1 |
| 4 | Three-state epistemic resolution | Phase 1 |
| 5 | API router endpoints | Phases 1-4 |

**Phase 1 is the minimum viable engine.** A researcher can ask "What treats malaria?" and get a confidence-rated, evidence-counted answer with source attribution. Phases 2-5 build on that foundation.

---

## 9. Design Decisions (locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Max traversal depth | 3 hops | Prevents runaway queries on dense graph sections |
| Confidence aggregation | `max()` across chain | One strong RCT outweighs ten weak case reports |
| Evidence counting | Sum across chain | Each independent source confirms = +1 |
| Bidirectional handling | `OR` in JOIN | No duplicated edges, no separate "reverse" table |
| Contradiction pairs | Hardcoded set | Bounded, predictable, not computed dynamically |
| SQL execution | Raw `text()` queries | Full CTE control, no ORM abstraction overhead |
| Cycle prevention | `ARRAY` path tracking | PostgreSQL arrays for visited-node tracking |

---

## 10. Out of Scope

- **pyDatalog / logic programming:** Deferred. May be added later for open-ended reasoning (e.g. Ùmà queries), but not part of engine core.
- **Embeddings / vector search:** Belongs to Litsi, not the engine. The engine is purely symbolic.
- **Real-time updates:** Engine queries run on committed data. No streaming/incremental updates.
- **Graph visualization:** Future frontend concern, not part of query engine.
