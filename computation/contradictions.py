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
    """Detect conflicting relationship types on the same entity pair."""
    entity_pairs = defaultdict(list)
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
