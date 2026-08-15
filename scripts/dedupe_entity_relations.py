import sys, os
from sqlalchemy import text
from app.database import SessionLocal


def main():
    db = SessionLocal()
    try:
        duplicate_groups = db.execute(text("""
            SELECT from_entity_id, to_entity_id, relationship_id,
                   array_agg(id ORDER BY id) AS ids
            FROM entity_relations
            GROUP BY from_entity_id, to_entity_id, relationship_id
            HAVING COUNT(*) > 1
            """)).fetchall()

        if not duplicate_groups:
            print("No duplicate entity_relations found.")
            return

        total_rows = db.execute(text("""
            SELECT SUM(group_size) FROM (
                SELECT COUNT(*) AS group_size
                FROM entity_relations
                GROUP BY from_entity_id, to_entity_id, relationship_id
                HAVING COUNT(*) > 1
            ) grouped
            """)).scalar()

        print(f"Found {len(duplicate_groups)} duplicate groups, {total_rows} rows total")

        if input("Proceed? (yes/no): ") != "yes":
            print("Aborted.")
            return

        for group in duplicate_groups:
            surviving_id = group.ids[0]
            dropped_ids = group.ids[1:]

            # Re-link all sources from the dropped rows
            db.execute(text("""
                UPDATE relationship_sources
                SET relationship_id = :surviving
                WHERE relationship_id = ANY(:dropped)
                """), {"surviving": surviving_id, "dropped": dropped_ids})

            # Deduplicate sources on (relationship_id, source_url)
            db.execute(text("""
                DELETE FROM relationship_sources
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY relationship_id, source_url
                            ORDER BY created_at ASC
                        ) AS rn
                        FROM relationship_sources
                        WHERE relationship_id = :surviving
                    ) AS numbered WHERE rn > 1
                )
                """), {"surviving": surviving_id})

            # Recompute evidence_count and confidence
            db.execute(text("""
                UPDATE entity_relations
                SET evidence_count = (
                    SELECT COUNT(*) FROM relationship_sources
                    WHERE relationship_id = :surviving
                ),
                confidence = (
                    SELECT MAX(confidence) FROM relationship_sources
                    WHERE relationship_id = :surviving
                )
                WHERE id = :surviving
                """), {"surviving": surviving_id})

            # Delete the drained duplicates
            db.execute(text("""
                DELETE FROM entity_relations
                WHERE id = ANY(:dropped)
                """), {"dropped": dropped_ids})

            print(f"Merged group -> kept relation id {surviving_id}, removed {len(dropped_ids)} duplicate(s)")

        db.commit()

        remaining = db.execute(text("""
            SELECT from_entity_id, to_entity_id, relationship_id, COUNT(*)
            FROM entity_relations
            GROUP BY from_entity_id, to_entity_id, relationship_id
            HAVING COUNT(*) > 1
            """)).fetchall()

        if not remaining:
            print("All duplicate entity_relations resolved.")
        else:
            print(f"WARNING: {len(remaining)} duplicate groups still remain.")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
