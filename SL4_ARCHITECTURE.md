# Computational Symbolic Engine — Architecture

**Date:** July 2026 (updated 2026-07-25)
**Decision:** Postgres recursive CTEs + plain Python (no logic-programming library)
**Status:** In progress

---

## 1. Overview

The Computational Symbolic Engine is Sankofa's symbolic reasoning layer. It answers multi-hop queries over the knowledge graph by traversing `entity_relations` edges using Postgres `WITH RECURSIVE` CTEs, then applying Python functions for evidence weighing, contradiction detection, and three-state epistemic resolution.

**What the engine does NOT do:** open-ended reasoning, unification-based backtracking search, or rule inference via an external library. The query catalog is bounded and fixed-shape — single-hop lookups, 2-3 hop chains (forward and backward), bidirectional neighborhood, path finding, evidence aggregation, contradiction checks, and (Layer 2/3) hand-written rule-based derivation. This is deliberate: bounded traversal is predictable and suitable for live query-serving.

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
- Table name is `entity_relations` throughout the codebase (not `entity_relationships` — that name appears only in earlier prose notes and is corrected here)

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
    er.relationship_id AS relationship_id,
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

`relationship_id` is returned alongside `relationship_type` so the citations layer can join to `relationship_sources` without a second lookup.

### 3.2 Fixed-Depth Recursive CTE (2-hop, forward)

Use case: "What drugs target pathways involved in diseases prevalent in Nigeria?"

```sql
WITH RECURSIVE traversal AS (
    -- Anchor: first hop from source
    SELECT
        er.from_entity_id,
        er.to_entity_id,
        er.relationship_id,
        er.confidence,
        er.evidence_count,
        1 AS depth,
        ARRAY[er.from_entity_id, er.to_entity_id] AS path,
        ARRAY[er.relationship_id] AS relationship_ids
    FROM entity_relations er
    JOIN relationship_types rt ON er.relationship_id = rt.id
    JOIN entities e ON er.from_entity_id = e.id
    WHERE e.name = :source_name
      AND rt.name = :first_relationship

    UNION ALL

    -- Recursive: follow second hop
    SELECT
        er.from_entity_id,
        er.to_entity_id,
        er.relationship_id,
        er.confidence,
        er.evidence_count,
        t.depth + 1,
        t.path || er.to_entity_id,
        t.relationship_ids || er.relationship_id
    FROM entity_relations er
    JOIN traversal t ON er.from_entity_id = t.to_entity_id
    JOIN relationship_types rt ON er.relationship_id = rt.id
    WHERE rt.name = :second_relationship
      AND t.depth < :max_depth
      AND er.to_entity_id != ALL(t.path)  -- cycle prevention
)
SELECT
    e1.name AS from_name,
    e2.name AS to_name,
    t.relationship_ids AS relationship_ids,
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

**Provenance (2026-07-25 fix):** `relationship_id` was previously carried as a scalar that got silently overwritten at each recursive step — a 2-hop answer only retained the *second* edge's ID, dropping the first hop's citation entirely. Fixed by accumulating `relationship_ids` as an array the same way `path` accumulates node IDs. The Python citations resolver must now join `relationship_sources` against every ID in the array, not a single value. This applies to every multi-hop query below.

### 3.2b Fixed-Depth Recursive CTE (2-hop, backward)

Use case: same shape as 3.2 but starting from a known target and walking backward — "What could plausibly cause X, working back through intermediate mechanisms?"

Same structure as 3.2, mirrored:
- Anchor matches on `to_entity_id` against `:target_name` instead of `from_entity_id` against `:source_name`
- Recursive join is `ON er.to_entity_id = t.from_entity_id` (extending backward), path/relationship_ids accumulate `er.from_entity_id` / `er.relationship_id` accordingly
- Cycle check is `er.from_entity_id != ALL(t.path)`

Not derivable by simply swapping direction labels on 3.2 — the join condition and accumulation direction both flip. Implemented as `TWO_HOP_BACKWARD_QUERY` in `queries.py`.

### 3.3 Bidirectional Neighborhood

Use case: "What is connected to malaria, within N hops, any direction?"

Canonical version is the recursive multi-depth form (the flat single-hop form from earlier drafts is superseded — depth=1 of this query covers that case):

```sql
WITH RECURSIVE neighborhood AS (
    SELECT DISTINCT ON (
        CASE WHEN er.from_entity_id = :entity_id THEN er.to_entity_id ELSE er.from_entity_id END
    )
        CASE WHEN er.from_entity_id = :entity_id THEN er.to_entity_id ELSE er.from_entity_id END AS connected_id,
        er.id AS relationship_id,
        rt.name AS relationship_type,
        CASE WHEN er.from_entity_id = :entity_id THEN 'outgoing' ELSE 'incoming' END AS direction,
        er.confidence,
        er.evidence_count,
        ARRAY[
            CASE WHEN er.from_entity_id = :entity_id THEN er.from_entity_id ELSE er.to_entity_id END
        ] AS path,
        1 AS depth
    FROM entity_relations er
    JOIN relationship_types rt ON er.relationship_id = rt.id
    WHERE er.from_entity_id = :entity_id OR er.to_entity_id = :entity_id

    UNION

    SELECT DISTINCT ON (
        CASE WHEN er.from_entity_id = n.connected_id THEN er.to_entity_id ELSE er.from_entity_id END
    )
        CASE WHEN er.from_entity_id = n.connected_id THEN er.to_entity_id ELSE er.from_entity_id END,
        er.id AS relationship_id,
        rt.name AS relationship_type,
        CASE WHEN er.from_entity_id = n.connected_id THEN 'outgoing' ELSE 'incoming' END,
        er.confidence,
        er.evidence_count,
        n.path || CASE WHEN er.from_entity_id = n.connected_id THEN er.to_entity_id ELSE er.from_entity_id END,
        n.depth + 1
    FROM entity_relations er
    JOIN neighborhood n ON (er.from_entity_id = n.connected_id OR er.to_entity_id = n.connected_id)
    JOIN relationship_types rt ON er.relationship_id = rt.id
    WHERE n.depth < :max_depth
      AND CASE WHEN er.from_entity_id = n.connected_id THEN er.to_entity_id ELSE er.from_entity_id END != ALL(n.path)
)
SELECT
    e.name AS entity_name,
    n.relationship_id,
    n.relationship_type,
    n.direction,
    n.confidence,
    n.evidence_count,
    n.depth
FROM neighborhood n
JOIN entities e ON n.connected_id = e.id
ORDER BY n.depth, e.name;
```

**Design decision (2026-07-25, supersedes earlier draft):** this query uses explicit `path`-array cycle prevention, the same pattern as 3.2 and 3.4 — not depth-bounding alone. An earlier draft relied only on `n.depth < :max_depth` with no path tracking; that's sufficient to guarantee termination but allows the same node to be revisited at a deeper level via a different route, producing duplicate/misleading entries in dense or cyclic graph regions. Path tracking is now standard across all three recursive traversal queries for consistency and to keep neighborhood results deduplicated per node.

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
        ps.visited || er.to_entity_id,
        ps.relationship_path || rt.name
    FROM entity_relations er
    JOIN path_search ps ON er.from_entity_id = ps.to_entity_id
    JOIN relationship_types rt ON er.relationship_id = rt.id
    WHERE ps.depth < :max_depth
      AND er.to_entity_id != ALL(ps.visited)
      AND ps.to_entity_id != :end_entity_id  -- stop expanding once target reached
)
SELECT
    e1.name AS from_name,
    e2.name AS to_name,
    ps.relationship_id AS relationship_id,
    ps.relationship_path,
    ps.depth
FROM path_search ps
JOIN entities e1 ON ps.from_entity_id = e1.id
JOIN entities e2 ON ps.to_entity_id = e2.id
WHERE ps.to_entity_id = :end_entity_id
ORDER BY ps.depth
LIMIT 1;
```

**Note:** this query still returns a scalar `relationship_id` (last hop only), same gap described in §3.2. `relationship_path` (the array of relationship *type names*) already accumulates correctly across hops — `relationship_id` should be upgraded to an array the same way once the citations resolver needs full-path provenance for path-finding results, not just chain results. Flagged as a follow-up, not yet applied here.

---

## 4. Python Layer

Operates on CTE query results. No ORM dependency — receives lists of dicts from raw SQL execution.

### 4.1 Evidence Weighing

**Design decision (2026-07-21, resolves earlier §10/§11 conflict):** the original single `weigh_chain()` used `max()` across a chain unconditionally. That's correct for aggregating multiple *independent sources confirming the same fact* (corroboration), but wrong for *combining different facts to derive a new one* (derivation) — `max()` would let a weak premise get laundered into a falsely-strong derived fact. These are split into two functions:

```python
TIER_SCORE = {1: 0.3, 2: 0.6, 3: 1.0}  # Traditional, Emerging, Established
DECAY = 0.75      # confidence discount applied per derivation hop
MAX_DEPTH = 3     # facts at this depth stop feeding further derivation


def aggregate_confidence(chain: list[dict]) -> int:
    """Return max confidence across a chain.
    Principle: one strong RCT (confidence=3) should outweigh
    ten weak case reports (confidence=1). Max, not average.
    """
    if not chain:
        return 0
    return max(r["confidence"] for r in chain)


def aggregate_evidence(chain: list[dict]) -> int:
    """Sum evidence_count across independent confirmations."""
    if not chain:
        return 0
    return sum(r["evidence_count"] for r in chain)


def weigh_chain(chain: list[dict]) -> dict:
    """
    Aggregate MULTIPLE INDEPENDENT SOURCES confirming the SAME fact
    (query-time corroboration — e.g. three papers all reporting
    'inhibits' between the same drug and protein). Max confidence,
    summed evidence.
    """
    return {
        "confidence": aggregate_confidence(chain),
        "evidence_count": aggregate_evidence(chain),
        "hop_count": len(chain),
    }


def score_to_tier(score: float) -> int:
    """Map a continuous derivation score back to a discrete tier."""
    if score >= 0.7:
        return 3
    if score >= 0.4:
        return 2
    return 1


def weigh_derived_fact(premises: list[dict]) -> dict:
    """
    Score a fact DERIVED by composing DIFFERENT premises — e.g.
    (A inhibits B) + (B causes C) => derived (A treats C). Not
    corroboration: a chain of reasoning can't be stronger than its
    weakest link, and every hop of inference is itself an unverified
    claim, so depth must cost confidence. min() across premises, then
    decay per hop, hard-capped so a derived fact can never exceed its
    weakest premise's tier — prevents confidence laundering.

    Returns "confidence" (int, discrete tier — matches entity_relations'
    confidence column AND the input shape premises expect, so a derived
    fact can be fed straight back in as a premise for a further hop
    with no remapping) plus "score" (raw float, for audit/ranking).
    """
    if not premises:
        return {"score": 0.0, "confidence": 0, "depth": 0}
    scores = [TIER_SCORE[p["confidence"]] for p in premises]
    combined = min(scores)
    depth = max((p.get("depth", 0) for p in premises), default=0) + 1
    score = combined * (DECAY ** depth)
    min_premise_tier = min(p["confidence"] for p in premises)
    derived_tier = min(score_to_tier(score), min_premise_tier)
    return {
        "score": round(score, 4),
        "confidence": derived_tier,
        "depth": depth,
    }
```

`aggregate_confidence` / `aggregate_evidence` / `weigh_chain` handle query-time corroboration (unchanged from the original draft — max confidence, summed evidence, across parallel results for the same fact). `weigh_derived_fact` is the new one, for rule-time derivation of new facts (min + decay + hard cap). These are two genuinely different operations that must never be interchanged — see the naming/scope distinction above.

**Cycle/runaway protection for derivation** (Layer 2/3 rule engine, not the query layer): `MAX_DEPTH = 3` stops facts at max depth from feeding further derivation; each derived fact stores `derived_from: list[fact_id]` and ancestry is walked backward before insert to reject direct cycles; a dedup check on `(subject, relation, object)` backstops duplicate inserts. See §11.

### 4.2 Contradiction Detection

```python
from collections import defaultdict

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
    """Detect conflicting relationship types on the same entity pair,
    including conflicts across reversed direction (A->B vs B->A).

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

Detects two kinds of conflicts:
1. **Same-direction:** A→B has type a AND A→B has type b (e.g. "X treats Y" AND "X contraindicated_with Y")
2. **Reverse-direction:** A→B has type a AND B→A has type b (e.g. "X inhibits Y" AND "Y activates X")

The `direction` field in each contradiction output indicates which kind was detected. Uses `frozenset` dedup to avoid checking the same undirected entity pair twice.

### 4.3 Three-State Epistemic Resolution

```python
from enum import Enum
from computation.weighing import aggregate_confidence, aggregate_evidence


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

    1. Known — relationship exists, backed by >= 1 source
    2. Knowably absent — domain was ingested, nothing found
    3. Uncharted — domain hasn't been ingested yet

    coverage_registry maps disease_name to a list of ingested source names.
    Only needed for full three-state support; can be None initially.
    """
    if query_results:
        return {
            "state": EpistemicState.KNOWN,
            "data": query_results,
            "confidence": aggregate_confidence(query_results),
            "evidence_count": aggregate_evidence(query_results),
        }

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

Calls `aggregate_confidence`/`aggregate_evidence` directly — this is query-time aggregation over parallel results (corroboration), not derivation. The docstring above must stay a plain string, not an f-string: `{disease_name: [source_names_ingested]}` was illustrative prose, and inside an f-string the colon is parsed as a format-spec separator, not a dict literal — an earlier draft had this as `f"""..."""` and it raised `TypeError` on every call before any real logic ran. Fixed 2026-07-25.

---

## 5. Query Executor

Bridges CTE SQL execution and Python logic. Uses raw SQL via SQLAlchemy's `execute()` (not ORM queries) for full CTE control.

Executors now pass `relationship_ids` (plural, array) through to the citations resolver for `execute_two_hop`, matching the §3.2 fix. `execute_single_hop` and `execute_neighborhood` already returned a single `relationship_id` correctly, since those are genuinely single-edge results. Executors call `aggregate_confidence`/`aggregate_evidence` (or `weigh_chain`, which bundles both) for aggregating result sets, per §4.1 — never `weigh_derived_fact`, which is reserved for rule-time derivation, not query-time responses.

---

## 6. API Endpoints

_(unchanged — see routers/engine.py: `/engine/query`, `/engine/chain`, `/engine/neighborhood`, `/engine/path`)_

---

## 7. Litsi Answer Object

The structured object the engine hands to Litsi (Layer 3). Every query endpoint returns this shape.

### Fields

**epistemic_state** — always present, even on empty results. `state`: one of `"Known"`, `"Knowably absent"`, `"Uncharted"`; `message`: optional string for absent/uncharted states.

**query_results** — list of relationship rows matching the query. Each row: `from_name`, `to_name`, `relationship_type`, `confidence` (int 1-3), `evidence_count` (int), `depth` (hop number). Empty list when epistemic_state is not Known.

**citations** — provenance trail, pulled from `relationship_sources` joined to `entity_relations` via `relationship_id` (or `relationship_ids` for multi-hop results — see §3.2 fix). Each citation: `source_name`, `source_url`, `source_author` (nullable), `source_title` (nullable), `confidence` (this source's own rating, int 1-3). For multi-hop chain results, citations must be resolved for every ID in `relationship_ids`, not just the terminal hop — this was a gap in the original CTEs, fixed 2026-07-25.

**contradictions** — list of detected conflict pairs from `contradictions.py` (§4.2). Same-direction and reverse-direction detection. Each contradiction includes a `direction` field ("same" or "reverse") indicating which kind was detected.

**chain_weight** — aggregation metadata for multi-hop query_results, computed by `weigh_chain()` (§4.1) — max confidence across the result set, summed evidence_count, hop_count. Null for single-hop queries. Not to be confused with derivation-time weighing (`weigh_derived_fact()`), which never appears in this object — derivation happens at ingestion/rule-execution time, not query time, and produces new stored facts rather than a query response.

---

## 8. File Structure

```
sankofa/
├── computation/
│   ├── __init__.py          # Package exports
│   ├── queries.py           # CTE SQL queries (text() strings)
│   ├── executor.py          # execute_single_hop, execute_two_hop, etc.
│   ├── weighing.py          # aggregate_confidence, aggregate_evidence, weigh_chain, weigh_derived_fact, TIER_SCORE, DECAY, MAX_DEPTH
│   ├── contradictions.py    # detect_contradictions, CONFLICT_PAIRS
│   ├── epistemic.py         # resolve_epistemic_state, EpistemicState enum
│   └── rules.py             # Layer 2/3 derivation rule functions (see §11)
└── routers/
    └── engine.py            # FastAPI router endpoints
```

---

## 9. Implementation Order

| Phase | What | Depends on |
|-------|------|------------|
| 1 | Single-hop CTE queries + Python evidence-weighing | Nothing |
| 2 | Fixed-depth recursive CTEs (2-3 hop, forward + backward) | Phase 1 |
| 3 | Contradiction detection logic | Phase 1 |
| 4 | Three-state epistemic resolution | Phase 1 |
| 5 | Bidirectional neighborhood + path finding | Phase 1-2 |
| 6 | Rule-based derivation (Layer 2/3) | Phases 1-5 |
| 7 | API router endpoints | Phases 1-6 |

**Phase 1 is the minimum viable engine.** A researcher can ask "What treats malaria?" and get a confidence-rated, evidence-counted answer with source attribution.

---

## 10. Design Decisions (locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Max traversal depth | 3 hops | Prevents runaway queries on dense graph sections |
| Confidence aggregation — corroboration | `max()` across independent sources | One strong RCT outweighs ten weak case reports |
| Confidence aggregation — derivation | `min()` across premises, then `DECAY` per hop, hard-capped | A derivation chain can't be stronger than its weakest premise, and inference itself must cost confidence — prevents laundering |
| Evidence counting | Sum across chain | Each independent source confirms = +1 |
| Bidirectional handling | `OR` in JOIN | No duplicated edges, no separate "reverse" table |
| Neighborhood cycle prevention | `ARRAY` path tracking (not depth-bound alone) | Consistent with 2-hop/path queries; prevents duplicate revisits in dense graphs |
| Contradiction pairs | Hardcoded set, same-direction + reverse-direction | Bounded, predictable; `direction` field distinguishes the two kinds |
| SQL execution | Raw `text()` queries | Full CTE control, no ORM abstraction overhead |
| Cycle prevention (traversal) | `ARRAY` path tracking | PostgreSQL arrays for visited-node tracking |
| Rule-based derivation | Plain Python functions, not DL/Datalog | See §11 |

`max()` and `min()` are answering different questions (corroboration vs. derivation) — see §4.1 for why they were previously conflated under one function and why that was a bug.

---

## 11. Rule-Based Reasoning (Layer 2/3)

**Decided:** Layer 2/3 reasoning is implemented as hand-written Python functions performing typed graph-edge composition over `entity_relations` — not a Description Logic reasoner (owlready2) or a Datalog engine (pyDatalog/ASP). Each rule is a plain function: pattern of existing relationship rows in, new derived relationship row out.

Confidence for derived facts uses `weigh_derived_fact()` (§4.1): `TIER_SCORE`, `min()` across premises, `DECAY = 0.75` per hop, hard-capped tier stored under the `confidence` key — deliberately matching both `entity_relations.confidence` and the key premises expect, so a derived fact can feed directly into a further hop with no remapping.

Cycle/runaway protection, three independent guards:
- `MAX_DEPTH = 3` — facts at max depth aren't used as premises for further derivation
- `derived_from: list[fact_id]` ancestry walked backward before insert, rejecting direct cycles
- Dedup check on `(subject, relation, object)` before any insert, as a backstop

**Why:** Sankofa's relationship types (causes, treats, inhibits, prevalent_in...) are directed weighted edges, not is-a/category relationships — DL's classification/subsumption machinery doesn't fit. Datalog/general rule engines solve a more general problem than the fixed, small set of composition patterns Sankofa needs. Owning the reasoning layer outright also avoids locking into a formalism that may not survive Layer 4 (Ùmà, indigenous-knowledge reasoning), which likely won't map cleanly onto classical DL categories.

**Rules out:** owlready2 (DL reasoner, built for is-a hierarchies Sankofa doesn't have). Datalog/ASP (pyDatalog, clingo — more general/complex than needed). SymPy (mathematics domain, not relational inference).

**Unblocks:** first rule to implement — `inhibits + causes → treats` (derived), tested on the malaria/anemia slice before generalizing to a rule-registration framework.

---

## 12. Out of Scope

- **pyDatalog / logic programming:** Deferred. May be added later for open-ended reasoning (e.g. Ùmà queries), but not part of engine core.
- **Embeddings / vector search:** Belongs to Litsi, not the engine. The engine is purely symbolic.
- **Real-time updates:** Engine queries run on committed data. No streaming/incremental updates.
- **Graph visualization:** Future frontend concern, not part of query engine.
- **Reverse-direction contradiction detection:** Implemented. Split into same-direction and reverse-direction checks, with `frozenset` dedup to avoid checking the same undirected pair twice. See §4.2.
- **Path-finding full-chain citations:** `relationship_id` in §3.4 is still scalar (last hop only); array upgrade not yet applied — see §3.4 note.
