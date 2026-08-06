from collections import defaultdict

CONFLICT_PAIRS = {
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
    including conflicts across reversed direction (A->B vs B->A)."""
    entity_pairs = defaultdict(list)
    for r in results:
        key = (r["from_entity_id"], r["to_entity_id"])
        entity_pairs[key].append(r)

    contradictions = []
    seen_pairs = set()

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
            # same-direction conflict (existing behavior)
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
            # reverse-direction conflict (new)
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
