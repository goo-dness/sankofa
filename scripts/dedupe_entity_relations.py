import sys, os
from sqlalchemy import text
from app.database import SessionLocal

def main():
    db = SessionLocal()
    try:
        duplicate_groups = db.execute(text("""
            SELECT from_entity_id, to_entity_id, relationship_id
            array_agg(id ORDER BY id) AS ids
            FROM entity_relations
            GROUP BY from_entity_id, to_entity_id, relationship_id
            HAVING COUNT(*) > 1
            """)).fetchall()
        if duplicate_groups is None:
            print(f"No duplicates entity_relations found.")
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
