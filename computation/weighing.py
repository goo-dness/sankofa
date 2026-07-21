def aggregate_confidence(chain):
    """Return max confidence across a chain.

    Principle: one strong RCT (confidence=3) should outweigh ten weak case reports (confidence=1). Max, not average.
    """
    if not chain:
        return 0
    return max(r["confidence"] for r in chain)

def aggregate_evidence(chain):
    """Sum evidence_count across independent confirmations

    Each new source that confirms a claim adds +1 to evidence_count.
    Summing across a chain gives total independent confirmations.
    """
    if not chain:
        return 0
    return sum(r["evidence_count"] for r in chain)

def weigh_chain(chain):
    """Aggregate confidence and evidence_count for a traversal chain"""
    return{
        "confidence": aggregate_confidence(chain),
        "evidence_count": aggregate_evidence(chain),
        "hop_count": len(chain),
    }
