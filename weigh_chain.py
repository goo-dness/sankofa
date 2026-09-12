from sqlalchemy import text

from app.database import SessionLocal
from computation.weighing import weigh_chain

db = SessionLocal()

results = (
    db.execute(
        text("""
        SELECT er.confidence, er.evidence_count
        FROM entity_relations er
        JOIN relationship_types rt ON er.relationship_id = rt.id
        JOIN entities d ON er.to_entity_id = d.id
        WHERE rt.name = 'treats'
          AND lower(trim(d.name)) = 'malaria'
        """)
    )
    .mappings()
    .all()
)
results = [dict(r) for r in results]

chain_result = weigh_chain(results)

print("Raw row count:", len(results))
print("weigh_chain result:", chain_result)

db.close()
