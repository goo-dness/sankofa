# One-time cleanup for `fake-contradictions`.
# Removes the protective_against / predisposes_to facts that the abstract scan wrote,
# plus their coverage rows. Curated (hand-verified) facts are never touched.
# Run from the repo root:  python3 -m scripts.remove_scan_directed_genetics

from sqlalchemy import text

from app.database import SessionLocal

TYPES = ["protective_against", "predisposes_to"]  # the two directed types
SCAN_SOURCES = ["OpenAlex", "PubMed"]  # sources that came from the abstract scan


def main():
    db = SessionLocal()
    try:
        # --- PREVIEW: count what would be deleted, before deleting anything ---
        relationship_count = db.execute(
            text("""
                SELECT COUNT(*) FROM entity_relations er
                JOIN relationship_types rt ON rt.id = er.relationship_id
                WHERE rt.name = ANY(:types)
                """),
            {"types": TYPES},
        ).scalar()

        source_count = db.execute(
            text("""
                SELECT COUNT(*) FROM relationship_sources rs
                JOIN entity_relations er ON er.id = rs.relationship_id
                JOIN relationship_types rt ON rt.id = er.relationship_id
                WHERE rt.name = ANY(:types) AND rs.source_name = ANY(:scan_sources)
                """),
            {"types": TYPES, "scan_sources": SCAN_SOURCES},
        ).scalar()

        coverage_count = db.execute(
            text("""
                SELECT COUNT(*) FROM ingestion_coverage
                WHERE relationship_type = ANY(:types)
                """),
            {"types": TYPES},
        ).scalar()

        print(f"Relationships of these types:   {relationship_count}")
        print(f"Scan-made source rows:          {source_count}")
        print(f"Coverage rows for these types:  {coverage_count}")

        if relationship_count == 0 and coverage_count == 0:
            print("Nothing to remove.")
            return

        # Same safety check as your other scripts: nothing changes without "yes".
        if input("Proceed with the delete? (yes/no): ").strip().lower() != "yes":
            print("Aborted.")
            return

        # --- 1. Delete the scan-made source rows for these two types ---
        db.execute(
            text("""
                DELETE FROM relationship_sources
                WHERE source_name = ANY(:scan_sources)
                  AND relationship_id IN (
                      SELECT er.id FROM entity_relations er
                      JOIN relationship_types rt ON rt.id = er.relationship_id
                      WHERE rt.name = ANY(:types)
                  )
                """),
            {"types": TYPES, "scan_sources": SCAN_SOURCES},
        )

        # --- 2. Delete relationships of these types that now have NO source left ---
        # A curated fact still has its Curated source, so it survives.
        db.execute(
            text("""
                DELETE FROM entity_relations
                WHERE relationship_id IN (
                          SELECT id FROM relationship_types WHERE name = ANY(:types)
                      )
                  AND NOT EXISTS (
                      SELECT 1 FROM relationship_sources rs
                      WHERE rs.relationship_id = entity_relations.id
                  )
                """),
            {"types": TYPES},
        )

        # --- 3. Delete their coverage rows (the scan no longer emits these types) ---
        # The curated loader never writes coverage, so every row here is scan-made.
        db.execute(
            text(
                "DELETE FROM ingestion_coverage WHERE relationship_type = ANY(:types)"
            ),
            {"types": TYPES},
        )

        db.commit()  # one commit: all three deletes succeed together or none do
        print("Cleanup complete.")

        # --- VERIFY: what remains of these types ---
        remaining = db.execute(
            text("""
                SELECT rt.name, COUNT(*) FROM entity_relations er
                JOIN relationship_types rt ON rt.id = er.relationship_id
                WHERE rt.name = ANY(:types)
                GROUP BY rt.name
                """),
            {"types": TYPES},
        ).fetchall()
        print(f"Remaining relationships of these types: {remaining or 'none'}")

    except Exception as e:
        db.rollback()  # undo everything if any step failed
        print(f"Error, nothing was deleted: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
