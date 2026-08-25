"""
merge_domain_duplicate_entities.py

Purpose
-------
Merge every entity created under the domain ``epidemiology`` (the WHO disease
records) into its counterpart that lives under the domain ``healthcare``
(OpenAlex / PubMed / ChEMBL). The merge follows a strict
"find-duplicates-repoint-dedupe-delete" workflow:

1. Find all `epidemiology` entities that have a case-insensitive name match in
   `healthcare`. If a match does **not** exist, the epidemiology row is simply
   retagged to `healthcare` so future ingestions will treat it as the canonical
   record.

2. For each pair that does have a match:
   * Re-point every `entity_relations` row that referenced the epidemiology
     entity (both **from** and **to** sides) to the healthcare survivor.
   * If the survivor already has an identical relationship, move its
     `relationship_sources` rows onto the survivor, dedupe them by
     (relationship_id, source_url), recompute the survivor's evidence_count/
     confidence from the real deduped rows, and delete the duplicate
     relationship.
   * Transfer the `entity_sources` rows, skipping any that already exist on the
     survivor (by unique `source_url`).
   * Re-compute the survivor's `evidence_count` (a true count of its sources) and
     keep the higher of the two confidence values.
   * Finally delete the now-empty epidemiology row.

3. After all merges are complete, sanity-check that no name is split across
   multiple domains.

The script is deliberately **idempotent** — you can run it repeatedly; rows
without a counterpart are only re-tagged, and duplicate relationships are never
re-created.

Usage
-----
    python -m scripts.merge_domain_duplicate_entities

The script will pause and ask for confirmation before making any changes.
"""

import sys
from sqlalchemy import text
from app.database import SessionLocal

# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------

def prompt_yes_no(message: str) -> bool:
    """Simple yes/no prompt — returns True only on an exact 'yes'."""
    resp = input(f"{message} (yes/no): ").strip().lower()
    return resp == "yes"

def log(msg: str, *args):
    """Minimal stdout logger — can be replaced by `logging` if desired."""
    print(msg.format(*args))

def merge_clashing_relationships(db, clashes):
    """Given rows with (dup_id, survivor_id), move relationship_sources onto
    the survivor, dedupe them by (relationship_id, source_url), recompute the
    survivor's evidence_count/confidence from the real deduped rows, then
    delete the now-redundant duplicate entity_relations row. Shared by both
    the FROM-side and TO-side clash handlers so the two stay in sync."""
    for clash in clashes:
        db.execute(
            text("""
                UPDATE relationship_sources
                SET    relationship_id = :survivor_id
                WHERE  relationship_id = :dup_id
            """),
            {"survivor_id": clash.survivor_id, "dup_id": clash.dup_id},
        )

        # dedupe: same source shouldn't count twice toward evidence_count
        db.execute(
            text("""
                DELETE FROM relationship_sources
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY relationship_id, source_url
                            ORDER BY created_at ASC
                        ) AS rn
                        FROM relationship_sources WHERE relationship_id = :survivor_id
                    ) ranked WHERE rn > 1
                )
            """),
            {"survivor_id": clash.survivor_id},
        )

        # recompute from the real, deduped source rows — never guessed or summed
        db.execute(
            text("""
                UPDATE entity_relations SET
                    evidence_count = (
                        SELECT COUNT(*) FROM relationship_sources WHERE relationship_id = :survivor_id
                    ),
                    confidence = (
                        SELECT MAX(confidence) FROM relationship_sources WHERE relationship_id = :survivor_id
                    )
                WHERE id = :survivor_id
            """),
            {"survivor_id": clash.survivor_id},
        )

        db.execute(
            text("DELETE FROM entity_relations WHERE id = :dup_id"),
            {"dup_id": clash.dup_id},
        )

# ----------------------------------------------------------------------
# Core merge routine
# ----------------------------------------------------------------------

def main() -> None:
    db = SessionLocal()

    try:
        # 1. Find all epidemiology-domain entities and a possible healthcare
        #    counterpart (case-insensitive name match).
        duplicate_pairs = db.execute(
            text("""
                SELECT e1.id   AS epi_id,
                       e1.name AS epi_name,
                       e2.id   AS healthcare_id
                FROM   entities e1
                LEFT JOIN entities e2
                  ON   LOWER(TRIM(e2.name)) = LOWER(TRIM(e1.name))
                 AND   e2.domain = 'healthcare'
                WHERE  e1.domain = 'epidemiology'
            """)
        ).fetchall()

        if not duplicate_pairs:
            log("No epidemiology-domain entities found — nothing to do.")
            return

        log("Found {} epidemiology-domain entities to process.", len(duplicate_pairs))

        # 2. Confirm before mutating any data.
        if not prompt_yes_no("Proceed with the merge?"):
            log("Aborted by user.")
            return

        # 3. Process each pair
        for pair in duplicate_pairs:
            epi_id = pair.epi_id
            epi_name = pair.epi_name
            healthcare_id = pair.healthcare_id

            # No healthcare counterpart — just retag the epidemiology row.
            if healthcare_id is None:
                db.execute(
                    text("UPDATE entities SET domain = 'healthcare' WHERE id = :epi_id"),
                    {"epi_id": epi_id},
                )
                log("Retagged '{}' (id={}) -> domain='healthcare'.", epi_name, epi_id)
                continue

            log("Merging '{}' (epi id={}) into healthcare id={}.", epi_name, epi_id, healthcare_id)

            # 3a. Repoint FROM side of relationships
            db.execute(
                text("""
                    UPDATE entity_relations
                    SET    from_entity_id = :healthcare_id
                    WHERE  from_entity_id = :epi_id
                      AND NOT EXISTS (
                        SELECT 1
                        FROM   entity_relations er2
                        WHERE  er2.from_entity_id = :healthcare_id
                           AND er2.to_entity_id   = entity_relations.to_entity_id
                           AND er2.relationship_id = entity_relations.relationship_id
                      )
                """),
                {"healthcare_id": healthcare_id, "epi_id": epi_id},
            )

            # 3b. Handle clashes on the FROM side (duplicate relationships)
            clashing_from = db.execute(
                text("""
                    SELECT er.id  AS dup_id,
                           er2.id AS survivor_id
                    FROM   entity_relations er
                    JOIN   entity_relations er2
                           ON er2.from_entity_id = :healthcare_id
                          AND er2.to_entity_id   = er.to_entity_id
                          AND er2.relationship_id = er.relationship_id
                    WHERE  er.from_entity_id = :epi_id
                """),
                {"healthcare_id": healthcare_id, "epi_id": epi_id},
            ).fetchall()

            merge_clashing_relationships(db, clashing_from)

            # 3c. Repoint TO side of relationships (mirror of 3a)
            db.execute(
                text("""
                    UPDATE entity_relations
                    SET    to_entity_id = :healthcare_id
                    WHERE  to_entity_id = :epi_id
                      AND NOT EXISTS (
                        SELECT 1
                        FROM   entity_relations er2
                        WHERE  er2.to_entity_id   = :healthcare_id
                           AND er2.from_entity_id = entity_relations.from_entity_id
                           AND er2.relationship_id = entity_relations.relationship_id
                      )
                """),
                {"healthcare_id": healthcare_id, "epi_id": epi_id},
            )

            # 3d. Handle clashes on the TO side (mirror of 3b — same helper)
            clashing_to = db.execute(
                text("""
                    SELECT er.id  AS dup_id,
                           er2.id AS survivor_id
                    FROM   entity_relations er
                    JOIN   entity_relations er2
                           ON er2.to_entity_id   = :healthcare_id
                          AND er2.from_entity_id = er.from_entity_id
                          AND er2.relationship_id = er.relationship_id
                    WHERE  er.to_entity_id = :epi_id
                """),
                {"healthcare_id": healthcare_id, "epi_id": epi_id},
            ).fetchall()

            merge_clashing_relationships(db, clashing_to)

            # 3e. Move entity_sources rows (skip duplicates by source_url)
            db.execute(
                text("""
                    UPDATE entity_sources
                    SET    entity_id = :healthcare_id
                    WHERE  entity_id = :epi_id
                      AND  source_url NOT IN (
                         SELECT source_url FROM entity_sources WHERE entity_id = :healthcare_id
                      )
                """),
                {"healthcare_id": healthcare_id, "epi_id": epi_id},
            )

            db.execute(
                text("DELETE FROM entity_sources WHERE entity_id = :epi_id"),
                {"epi_id": epi_id},
            )

            # 3f. Re-compute evidence_count & pick the higher confidence
            db.execute(
                text("""
                    UPDATE entities
                    SET    evidence_count = (
                             SELECT COUNT(*) FROM entity_sources WHERE entity_id = :healthcare_id
                           ),
                           confidence = GREATEST(
                             confidence,
                             (SELECT confidence FROM entities WHERE id = :epi_id)
                           )
                    WHERE  id = :healthcare_id
                """),
                {"healthcare_id": healthcare_id, "epi_id": epi_id},
            )

            # 3g. Delete the now-empty epidemiology row
            db.execute(
                text("DELETE FROM entities WHERE id = :epi_id"),
                {"epi_id": epi_id},
            )

            log("Merged '{}' (epi id={}) -> kept healthcare id={}.", epi_name, epi_id, healthcare_id)

        # 4. Commit everything
        db.commit()
        log("All merges committed successfully.")

        # 5. Verify that no name is still split across multiple domains
        remaining = db.execute(
            text("""
                SELECT name, COUNT(DISTINCT domain) AS domain_count
                FROM   entities
                GROUP BY name
                HAVING COUNT(DISTINCT domain) > 1
            """)
        ).fetchall()

        if not remaining:
            log("All domain duplicates resolved — every name now lives in a single domain.")
        else:
            log("WARNING: {} name(s) still appear in >1 domain:", len(remaining))
            for row in remaining:
                log(" - {} (domains: {})", row.name, row.domain_count)

    except Exception as exc:
        db.rollback()
        log("Error encountered, transaction rolled back:\n{}", exc)
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
