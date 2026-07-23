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

    Detects two kinds of conflicts:
    1. Same-direction: A→B has type a AND A→B has type b
       Example: "X treats Y" AND "X contraindicated_with Y"
    2. Reverse-direction: A→B has type a AND B→A has type b
       Example: "X inhibits Y" AND "Y activates X"

    Uses undirected dedup (frozenset) to avoid checking the same
    entity pair twice from both directions.
    """
    entity_pairs: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for r in results:
        key = (r["from_entity_id"], r["to_entity_id"])
        entity_pairs[key].append(r)

    contradictions = []
    seen_pairs: set[frozenset] = set()

    for pair_key, relationships in entity_pairs.items():
        from_id, to_id = pair_key
        reverse_key = (to_id, from_id)

        # avoid checking the same undirected pair twice
        undirected_key = frozenset(pair_key)
        if undirected_key in seen_pairs:
            continue
        seen_pairs.add(undirected_key)

        same_dir_types = {r["relationship_type"] for r in relationships}
        reverse_relationships = entity_pairs.get(reverse_key, [])
        reverse_dir_types = {r["relationship_type"] for r in reverse_relationships}

        for conflict in CONFLICT_PAIRS:
            a, b = conflict
            # same-direction conflict
            if a in same_dir_types and b in same_dir_types:
                contradictions.append({
                    "from_entity_id": from_id,
                    "to_entity_id": to_id,
                    "conflicting_types": list(conflict),
                    "direction": "same",
                    "relationships": [
                        r for r in relationships if r["relationship_type"] in conflict
                    ],
                })
            # reverse-direction conflict
            if a in same_dir_types and b in reverse_dir_types:
                contradictions.append({
                    "from_entity_id": from_id,
                    "to_entity_id": to_id,
                    "conflicting_types": list(conflict),
                    "direction": "reverse",
                    "relationships": [
                        r for r in relationships if r["relationship_type"] == a
                    ] + [
                        r for r in reverse_relationships if r["relationship_type"] == b
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

## 7. Litsi Answer Object

The structured object the engine hands to Litsi (Layer 3). Every query endpoint returns this shape. Litsi consumes it directly — no transformation needed on the AI layer side.

### Fields

**epistemic_state** — always present, even on empty results. Contains:
- `state`: one of `"Known"`, `"Knowably absent"`, `"Uncharted"` (from EpistemicState enum)
- `message`: optional string, populated for absent/uncharted states with explanation

**query_results** — list of relationship rows matching the query. Each row contains:
- `from_name`, `to_name`: entity names (strings)
- `relationship_type`: the edge label (string)
- `confidence`: int 1-3
- `evidence_count`: int
- `depth`: hop number (1 for single-hop, 2+ for multi-hop)

Empty list when epistemic_state is not Known.

**citations** — provenance trail. Each citation contains:
- `source_name`: human-readable source label (string)
- `source_url`: link to the original source (string)
- `source_author`: paper author name (string | null — not every source has one, e.g. WHO GHO indicators)
- `source_title`: paper title (string | null — same nullable reason)
- `confidence`: this specific source's own confidence rating (int 1-3)

Pulled from `relationship_sources` joined to `entity_relations` during the CTE query. Litsi needs full author + title data to produce publication-usable attributions — source name and URL alone aren't enough (CONTEXT.md §7 decision).

**contradictions** — list of detected conflict pairs. Each contradiction contains:
- `from_entity_id`, `to_entity_id`: the entity pair (ints)
- `conflicting_types`: the two conflicting relationship type names (list of 2 strings)
- `relationships`: the actual relationship rows involved (list of dicts)

Empty list when no contradictions found. Detection logic lives in `contradictions.py` (§4.2).

**chain_weight** — aggregation metadata for multi-hop queries. Contains:
- `confidence`: max confidence across the chain (int)
- `evidence_count`: sum of evidence counts across the chain (int)
- `hop_count`: number of hops traversed (int)

Null for single-hop queries (no chain to weigh). Populated by `weigh_chain()` from `weighing.py` (§4.1).

### Why this matters

This object is the contract between the engine and Litsi. The engine computes it; Litsi interprets and explains it. Keeping the schema explicit in the architecture doc means both sides agree on what fields exist, what types they carry, and where the data comes from — no ambiguity when Litsi's RAG pipeline connects to the PostgreSQL backend.

---

## 8. File Structure

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

## 9. Implementation Order

| Phase | What | Depends on |
|-------|------|------------|
| 1 | Single-hop CTE queries + Python evidence-weighing | Nothing |
| 2 | Fixed-depth recursive CTEs (2-3 hop) | Phase 1 |
| 3 | Contradiction detection logic | Phase 1 |
| 4 | Three-state epistemic resolution | Phase 1 |
| 5 | API router endpoints | Phases 1-4 |

**Phase 1 is the minimum viable engine.** A researcher can ask "What treats malaria?" and get a confidence-rated, evidence-counted answer with source attribution. Phases 2-5 build on that foundation.

---

## 10. Design Decisions (locked)

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

## 11. Rule-Based Reasoning (Layer 2/3)

**Decided:** Layer 2/3 reasoning is implemented as hand-written Python
functions performing typed graph-edge composition over
entity_relationships — not a Description Logic reasoner (owlready2)
or a Datalog engine (pyDatalog/ASP). Each rule is a plain function:
pattern of existing relationship rows in, new derived relationship
row out.

Confidence for derived facts uses a continuous score alongside the
existing discrete tier:
- `TIER_SCORE = {1: 0.3, 2: 0.6, 3: 1.0}` (Traditional/Emerging/Established)
- `combined = min(score(premise_a), score(premise_b))` — a chain is
  only as strong as its weakest premise
- `derived_score = combined * (DECAY ** depth)`, `DECAY = 0.75` global
  constant, `depth = max(premise_a.depth, premise_b.depth) + 1`
- Score maps back to a tier for storage/display (`>=0.7 → 3`,
  `>=0.4 → 2`, else `1`), but a derived fact's tier can never exceed
  `min(premise tiers)` regardless of score — hard cap against
  confidence laundering across chains.

Cycle/runaway protection, three independent guards:
- `MAX_DEPTH = 3` global constant — facts at max depth aren't used
  as premises for further derivation
- Each derived fact stores `derived_from: list[fact_id]`; before
  insert, ancestry is walked backward to reject a new
  `(subject, relation, object)` that already appears upstream
- Dedup check on `(subject, relation, object)` before any insert,
  observed or derived, as a backstop against duplicate rows

**Why:** Sankofa's relationship types (causes, treats, inhibits,
prevalent_in...) are directed weighted edges, not is-a/category
relationships — DL's classification/subsumption machinery doesn't
fit the data. Datalog/general rule engines solve a more general
problem than the fixed, small set of composition patterns Sankofa
actually needs. Owning the reasoning layer outright also avoids
locking into a formalism that may not survive Layer 4 (Ùmà,
indigenous-knowledge reasoning), which likely won't map cleanly onto
classical DL categories anyway.

**Rules out:** owlready2 (Description Logic reasoner) — rejected,
built for is-a/category hierarchies Sankofa doesn't have. Datalog/ASP
(pyDatalog, clingo) — rejected as more general/complex than needed.
SymPy — out of scope, that's for the mathematics domain, not relational
inference.

**Unblocks:** Layer 2 rule functions can be written directly against
the existing entity_relationships schema — first rule to implement:
`inhibits + causes → treats` (derived), tested on the malaria/anemia
slice before generalizing to a rule-registration framework.

---

## 12. Out of Scope

- **pyDatalog / logic programming:** Deferred. May be added later for open-ended reasoning (e.g. Ùmà queries), but not part of engine core.
- **Embeddings / vector search:** Belongs to Litsi, not the engine. The engine is purely symbolic.
- **Real-time updates:** Engine queries run on committed data. No streaming/incremental updates.
- **Graph visualization:** Future frontend concern, not part of query engine.
