# One-time cleanup for "Mosquitoes, blackflies and bats stored as disease causes".
# Removes the 18 `causes` relationships whose from-entity is really a vector,
# reservoir or intermediate host, not a pathogen. Confirmed by hand: none of
# the 75 causal_path derived facts depend on these 18 rows.
# Run from the repo root:  python3 -m scripts.remove_scan_vectors_as_causes

from sqlalchemy import text

from app.database import SessionLocal

# The 18 relationship ids confirmed in the issue log (2026-09-21).
BAD_RELATIONSHIP_IDS = [
    4293,
    4119,
    4259,
    4281,
    4225,
    4231,
    4260,
    4388,
    4289,
    4395,
    4117,
    4254,
    4394,
    4233,
    4267,
    4307,
    4403,
    4402,
]


def main():
    db = SessionLocal()
    try:
        # --- PREVIEW: show exactly what would be deleted, before deleting anything ---
        preview = db.execute(
            text("""
                SELECT er.id, f.name AS agent, t.name AS disease, er.evidence_count
                FROM entity_relations er
                JOIN entities f ON f.id = er.from_entity_id
                JOIN entities t ON t.id = er.to_entity_id
                WHERE er.id = ANY(:ids)
                ORDER BY er.evidence_count DESC
                """),
            {"ids": BAD_RELATIONSHIP_IDS},
        ).fetchall()

        if not preview:
            print("None of these relationship ids exist. Nothing to do.")
            return

        total_evidence = sum(row.evidence_count for row in preview)
        print(f"Found {len(preview)} relationships, {total_evidence} evidence total:")
        for row in preview:
            print(
                f"  id {row.id}: {row.agent} -> causes -> {row.disease} (evidence {row.evidence_count})"
            )

        # Same safety check as your other scripts: nothing changes without "yes".
        if input("\nProceed with the delete? (yes/no): ").strip().lower() != "yes":
            print("Aborted.")
            return

        # --- 1. Delete their citation rows first ---
        # A relationship can't be deleted while relationship_sources still points at it.
        db.execute(
            text("DELETE FROM relationship_sources WHERE relationship_id = ANY(:ids)"),
            {"ids": BAD_RELATIONSHIP_IDS},
        )

        # --- 2. Delete the relationships themselves ---
        db.execute(
            text("DELETE FROM entity_relations WHERE id = ANY(:ids)"),
            {"ids": BAD_RELATIONSHIP_IDS},
        )

        db.commit()  # one commit: both deletes succeed together or neither does
        print("Cleanup complete.")

        # --- VERIFY: none of these ids should exist anymore ---
        remaining = db.execute(
            text("SELECT COUNT(*) FROM entity_relations WHERE id = ANY(:ids)"),
            {"ids": BAD_RELATIONSHIP_IDS},
        ).scalar()
        print(f"Remaining rows with these ids: {remaining}")

    except Exception as e:
        db.rollback()  # undo everything if any step failed
        print(f"Error, nothing was deleted: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
