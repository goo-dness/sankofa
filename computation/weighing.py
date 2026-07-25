TIER_SCORE = {1: 0.3, 2: 0.6, 3: 1.0}
DECAY = 0.75
MAX_DEPTH = 3



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


def score_to_tier(score: float) -> int:
    """Map continuous score back to discrete tier."""
    if score >= 0.7:
        return 3
    if score >= 0.4:
        return 2
    return 1

def weigh_derived_fact(premises: list[dict]) -> dict:
    """
    Score a derived fact from its premises.
    Each premise dict must have:
        - "confidence": int(1-3), the discrete tier
        - "depth": int, how many hops deep this premise itself is (0 if observed)

    Returns:
        - "score": float, the continuous derived score
        - "confidence": int, the discrete tier (capped by min premise tiers)
        - "depth": int, the depth of the derived fact
    """

    if not premises:
        return{
            "score": 0.0,
            "tier": 0,
            "depth": 0
        }

    scores = [TIER_SCORE[p["confidence"]] for p in premises]
    combined = min(scores)
    depth = max((p.get("depth", 0) for p in premises), default=0) + 1
    score = combined * (DECAY ** depth)

    # tier cap: derived fact can never exceed min(premise tier)
    min_premise_tier = min(p["confidence"] for p in premises)
    derived_tier = min(score_to_tier(score), min_premise_tier)

    return {
        "score": round(score, 4),
        "confidence": derived_tier,
        "depth": depth,
    }
