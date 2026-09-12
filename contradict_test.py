from sqlalchemy import text

from app.database import SessionLocal
from computation.contradictions import detect_contradictions

db = SessionLocal()

# Pull relationship row with entity IDs + relationship type name
ALL_RELATIONSHIPS_QUERY = """
    SELECT er.from_entity_id, er.to_entity_id, rt.name AS relationship_type, er.confidence, er.evidence_count
    FROM entity_relations er
    JOIN relationship_types rt ON er.relationship_id = rt.id
"""

results = db.execute(text(ALL_RELATIONSHIPS_QUERY)).mappings().all()
results = [dict(r) for r in results]

contradictions = detect_contradictions(results)

print("Total relationships checked:", len(results))
print("Contradictions found:", len(contradictions))
for c in contradictions:
    print(c)
# Also check for any bidirectional (A,B)/(B,A) pairs, informally
pairs = {(r["from_entity_id"], r["to_entity_id"]) for r in results}
bidirectional = [(a, b) for (a, b) in pairs if (b, a) in pairs and a != b]
print("Bidirectional entity pairs found:", len(bidirectional))

db.close()
