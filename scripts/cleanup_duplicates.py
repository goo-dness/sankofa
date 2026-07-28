#!/usr/bin/env python3
"""
One-time script to deduplicate entities table on (lower(trim(name)), domain).
Run BEFORE adding the unique index migration.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal


def main():
    db = SessionLocal()
    try:
        # Find duplicate groups
        dupes = db.execute(text("""
            SELECT lower(trim(name)) AS norm_name, domain, 
                   array_agg(id ORDER BY confidence DESC, evidence_count DESC, id) AS ids
            FROM entities
            GROUP BY lower(trim(name)), domain
            HAVING COUNT(*) > 1
        """)).fetchall()

        if not dupes:
            print("No duplicates found. Nothing to clean up.")
            return

        print(f"Found {len(dupes)} duplicate groups:")
        for row in dupes:
            print(f"  {row.norm_name} ({row.domain}): {row.ids}")

        # Confirm before proceeding
        confirm = input("\nProceed with merge & delete? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return

        for row in dupes:
            ids = row.ids
            keep_id = ids[0]
            delete_ids = ids[1:]

            if not delete_ids:
                continue

            print(f"\nMerging {row.norm_name} ({row.domain}): keep {keep_id}, delete {delete_ids}")

            # Update FKs in entity_relations
            db.execute(text("""
                UPDATE entity_relations 
                SET from_entity_id = :keep 
                WHERE from_entity_id = ANY(:del)
            """), {"keep": keep_id, "del": delete_ids})

            db.execute(text("""
                UPDATE entity_relations 
                SET to_entity_id = :keep 
                WHERE to_entity_id = ANY(:del)
            """), {"keep": keep_id, "del": delete_ids})

            # Update FKs in entity_sources
            db.execute(text("""
                UPDATE entity_sources 
                SET entity_id = :keep 
                WHERE entity_id = ANY(:del)
            """), {"keep": keep_id, "del": delete_ids})

            # Merge evidence_count onto kept entity
            db.execute(text("""
                UPDATE entities 
                SET evidence_count = evidence_count + (
                    SELECT COALESCE(SUM(evidence_count), 0) 
                    FROM entities 
                    WHERE id = ANY(:del)
                ) 
                WHERE id = :keep
            """), {"keep": keep_id, "del": delete_ids})

            # Delete duplicate entities
            db.execute(text("DELETE FROM entities WHERE id = ANY(:del)"), {"del": delete_ids})

        db.commit()
        print("\nCleanup complete. Verifying...")

        # Verify
        remaining = db.execute(text("""
            SELECT lower(trim(name)), domain, COUNT(*) 
            FROM entities 
            GROUP BY lower(trim(name)), domain 
            HAVING COUNT(*) > 1
        """)).fetchall()

        if remaining:
            print(f"WARNING: {len(remaining)} groups still have duplicates!")
            for r in remaining:
                print(f"  {r[0]} ({r[1]}): {r[2]}")
        else:
            print("All duplicates resolved. Ready for unique index migration.")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()