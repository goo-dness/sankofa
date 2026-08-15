import sys, os
from sqlalchemy import text
from app.database import SessionLocal
from ingestions.openalex import ORGANISM_NAME_MAP


def main():
    db = SessionLocal()
    try:
        rows_to_process = []
        for informal_name, formal_name in ORGANISM_NAME_MAP.items():
            informal_row = db.execute(text("""
                SELECT id FROM entities
                WHERE lower(trim(name)) = :name
                AND entity_type = 'CausalAgent' AND domain = 'healthcare'
                """), {"name": informal_name}).fetchone()

            if informal_row is not None:
                formal_row = db.execute(text("""
                    SELECT id FROM entities
                    WHERE lower(trim(name)) = :name
                    AND entity_type = 'CausalAgent' AND domain = 'healthcare'
                    """), {"name": formal_name}).fetchone()
                rows_to_process.append({
                    "informal_name": informal_name,
                    "formal_name": formal_name,
                    "informal_id": informal_row.id,
                    "formal_id": formal_row.id if formal_row else None
                })

        if not rows_to_process:
            print("No informal CausalAgent names found.")
            return

        print(f"Found {len(rows_to_process)} names to fix:")
        for item in rows_to_process:
            if item["formal_id"] is None:
                print(f"  RENAME: '{item['informal_name']}' -> '{item['formal_name']}' (id {item['informal_id']})")
            else:
                print(f"  MERGE: '{item['informal_name']}' (id {item['informal_id']}) INTO '{item['formal_name']}' (id {item['formal_id']})")

        confirm = input("Proceed? (yes/no): ")
        if confirm != "yes":
            print("Aborted")
            return

        for item in rows_to_process:
            if item["formal_id"] is None:
                db.execute(text("""
                    UPDATE entities SET name = :formal_name WHERE id = :id
                    """), {"formal_name": item["formal_name"], "id": item["informal_id"]})
                print(f"Renamed id {item['informal_id']} to '{item['formal_name']}'")
                continue

            # Merge case
            keep_id = item["formal_id"]
            drop_id = item["informal_id"]

            # Relink entity_relations, both directions
            db.execute(text("""
                UPDATE entity_relations SET from_entity_id = :keep
                WHERE from_entity_id = :drop
                """), {"keep": keep_id, "drop": drop_id})
            db.execute(text("""
                UPDATE entity_relations SET to_entity_id = :keep
                WHERE to_entity_id = :drop
                """), {"keep": keep_id, "drop": drop_id})

            # Relink entity_sources onto the surviving entity
            db.execute(text("""
                UPDATE entity_sources SET entity_id = :keep
                WHERE entity_id = :drop
                """), {"keep": keep_id, "drop": drop_id})

            # Dedupe entity_sources on (entity_id, source_url) — keep earliest row
            db.execute(text("""
                DELETE FROM entity_sources
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY entity_id, source_url
                            ORDER BY created_at ASC
                        ) AS rn
                        FROM entity_sources WHERE entity_id = :keep
                    ) ranked WHERE rn > 1
                )
                """), {"keep": keep_id})

            # Recompute evidence_count from the real deduped table —
            # not SUM, since overlap between the two entities' sources
            # is expected here, not incidental
            db.execute(text("""
                UPDATE entities SET evidence_count = (
                    SELECT COUNT(*) FROM entity_sources
                    WHERE entity_id = :keep
                ) WHERE id = :keep
                """), {"keep": keep_id})

            # Dedupe entity_relations that now collide on
            # (from_entity_id, to_entity_id, relationship_id)
            duplicate_rel_groups = db.execute(text("""
                SELECT from_entity_id, to_entity_id, relationship_id, array_agg(id ORDER BY id) AS ids
                FROM entity_relations
                WHERE from_entity_id = :keep OR to_entity_id = :keep
                GROUP BY from_entity_id, to_entity_id, relationship_id
                HAVING COUNT(*) > 1
                """), {"keep": keep_id}).fetchall()

            for group in duplicate_rel_groups:
                surviving_id = group.ids[0]
                dropped_ids = group.ids[1:]

                db.execute(text("""
                    UPDATE relationship_sources SET relationship_id = :surviving
                    WHERE relationship_id = ANY(:dropped)
                    """), {"surviving": surviving_id, "dropped": dropped_ids})

                db.execute(text("""
                    DELETE FROM relationship_sources
                    WHERE id IN (
                        SELECT id FROM (
                            SELECT id, ROW_NUMBER() OVER (
                                PARTITION BY relationship_id, source_url
                                ORDER BY created_at ASC
                            ) AS rn
                            FROM relationship_sources WHERE relationship_id = :surviving
                        ) ranked WHERE rn > 1
                    )
                    """), {"surviving": surviving_id})

                db.execute(text("""
                    UPDATE entity_relations SET
                        evidence_count = (SELECT COUNT(*) FROM relationship_sources WHERE relationship_id = :surviving),
                        confidence = (SELECT MAX(confidence) FROM relationship_sources WHERE relationship_id = :surviving)
                    WHERE id = :surviving
                    """), {"surviving": surviving_id})

                db.execute(text("""
                    DELETE FROM entity_relations WHERE id = ANY(:dropped)
                    """), {"dropped": dropped_ids})

            # Delete the now fully drained informal entity —
            # runs once per item regardless of whether there were
            # any duplicate relationship groups above
            db.execute(text("""
                DELETE FROM entities WHERE id = :drop
                """), {"drop": drop_id})
            print(f"Merged '{item['informal_name']}' into '{item['formal_name']}'")

        db.commit()

        print("Verifying no informal names remain...")
        remaining = db.execute(text("""
            SELECT lower(trim(name)) FROM entities
            WHERE lower(trim(name)) = ANY(:informal_names)
            """), {"informal_names": list(ORGANISM_NAME_MAP.keys())}).fetchall()

        if remaining:
            print(f"WARNING: informal names still present: {remaining}")
        else:
            print("All informal names resolved")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
