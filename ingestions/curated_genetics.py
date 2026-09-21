# Hand-verified genetic associations that have a DIRECTION (protective / predisposes).
# Same extract -> transform -> load pattern as the other ingestions.
# The rows themselves live in data/genetic_associations.py.

from typing import Any, Dict, List, Tuple

from sqlalchemy import func

from app.database import SessionLocal
from data.genetic_associations import GENETIC_ASSOCIATIONS
from models.entities import Entity
from models.entity_relationships import EntityRelations
from models.entity_sources import EntitySource
from models.relations_type import RelationshipTypes
from models.relationship_sources import RelationshipSource

# CONSTANTS
DOMAIN = "healthcare"  # same domain the other pipelines use
GENETIC_FACTOR_ENTITY_TYPE = "GeneticFactor"  # same type the scan uses
ALLOWED_DIRECTIONS = {"protective_against", "predisposes_to"}  # only these two here
SOURCE_NAME = "Curated"  # marks these facts as hand-checked, not scanned


def find_entity(db_session, name, domain):
    # Same lookup rule as the other load() functions: lowercase + trimmed name + domain.
    normalized = name.lower().strip()
    return (
        db_session.query(Entity)
        .filter(func.lower(func.trim(Entity.name)) == normalized)
        .filter_by(domain=domain)
        .first()
    )


def extract() -> List[Dict[str, Any]]:
    # The "source" is a local table, so this stage cannot fail.
    return list(GENETIC_ASSOCIATIONS)


def transform(
    raw_rows: List[Dict[str, Any]],
) -> Tuple[List[dict], List[dict], List[dict]]:
    entities = []
    relationships = []
    sources = []

    for row in raw_rows:
        label = f"{row['factor']} -> {row['disease']} ({row['relationship']})"

        # Guard 1: no source, no fact. This rule protects the graph.
        if not row["source_url"].strip():
            print(f"SKIP (no source yet): {label}")
            continue

        # Guard 2: only the two directed types are allowed in this table.
        if row["relationship"] not in ALLOWED_DIRECTIONS:
            print(f"SKIP (direction not allowed): {label}")
            continue

        # Guard 3: confidence must be a real tier.
        if row["confidence"] not in (1, 2, 3):
            print(f"SKIP (confidence must be 1, 2 or 3): {label}")
            continue

        # The genetic factor entity (the disease is never created here).
        entities.append(
            {
                "name": row["factor"],
                "domain": DOMAIN,
                "entity_type": GENETIC_FACTOR_ENTITY_TYPE,
                "expression": row["context"],
                "confidence": row["confidence"],
                "contributor": SOURCE_NAME,
            }
        )

        # The factor's own provenance: which paper vouches for it.
        sources.append(
            {
                "entity_name": row["factor"],
                "domain": DOMAIN,
                "source_name": SOURCE_NAME,
                "source_url": row["source_url"],
                "source_author": row["source_author"] or None,
                "source_title": row["source_title"] or None,
            }
        )

        # The directed fact itself, carrying its own citation.
        relationships.append(
            {
                "from_entity_name": row["factor"],
                "from_entity_domain": DOMAIN,
                "to_entity_name": row["disease"],
                "to_entity_domain": DOMAIN,
                "relationship": row["relationship"],
                "confidence": row["confidence"],
                "context": row["context"],
                "source_name": SOURCE_NAME,
                "source_url": row["source_url"],
                "source_author": row["source_author"] or None,
                "source_title": row["source_title"] or None,
            }
        )

    return entities, relationships, sources


def load(entities, relationships, sources, db_session):
    entity_name_to_id = {}  # links relationships to ids without extra queries

    try:
        # --- Stage 1: relationship type ids ---
        # Unlike the scans, we do NOT auto-create types here: a typo in the table
        # must be skipped, not turned into a new relationship type.
        relationship_type_name_to_id = {
            rt.name: rt.id for rt in db_session.query(RelationshipTypes).all()
        }

        # --- Stage 2: keep only facts whose disease is already in the graph ---
        valid_relationships = []
        for r in relationships:
            disease = find_entity(
                db_session, r["to_entity_name"], r["to_entity_domain"]
            )
            if disease is None:
                print(
                    f"Warning: disease '{r['to_entity_name']}' not in graph, skipping {r['from_entity_name']}"
                )
                continue
            if r["relationship"] not in relationship_type_name_to_id:
                print(
                    f"Warning: relationship type '{r['relationship']}' not in DB, skipping"
                )
                continue
            entity_name_to_id[(r["to_entity_name"], r["to_entity_domain"])] = disease.id
            valid_relationships.append(r)

        # Only create factors that still have a valid fact (no orphan entities).
        valid_factor_names = {r["from_entity_name"] for r in valid_relationships}

        # --- Stage 3: upsert the genetic factor entities ---
        for entity_dict in entities:
            entity_name = entity_dict["name"]
            domain = entity_dict["domain"]
            if entity_name not in valid_factor_names:
                continue

            existing_entity = find_entity(db_session, entity_name, domain)
            if existing_entity:
                if entity_dict["confidence"] > existing_entity.confidence:
                    existing_entity.confidence = entity_dict["confidence"]
                    print(f"Upgrade confidence for entity: {entity_name}")
                entity_name_to_id[(entity_name, domain)] = existing_entity.id
            else:
                # Starts at 0 because Stage 4 adds +1 for each new source,
                # so one source = evidence_count 1.
                new_entity = Entity(**entity_dict, evidence_count=0)
                db_session.add(new_entity)
                db_session.flush()  # get the new id before moving on
                entity_name_to_id[(entity_name, domain)] = new_entity.id
                print(f"Added new entity: {entity_name}")

        # --- Stage 4: upsert entity sources ---
        for source_dict in sources:
            entity_name = source_dict["entity_name"]
            domain = source_dict["domain"]
            if entity_name not in valid_factor_names:
                continue
            entity_id = entity_name_to_id.get((entity_name, domain))
            if not entity_id:
                continue

            existing_source = (
                db_session.query(EntitySource)
                .filter_by(entity_id=entity_id, source_url=source_dict["source_url"])
                .first()
            )
            if not existing_source:
                db_session.add(
                    EntitySource(
                        entity_id=entity_id,
                        source_name=source_dict["source_name"],
                        source_url=source_dict["source_url"],
                        source_author=source_dict.get("source_author"),
                        source_title=source_dict.get("source_title"),
                    )
                )
                entity = db_session.query(Entity).filter_by(id=entity_id).first()
                entity.evidence_count += 1
                print(
                    f"Added new source for {entity_name}: {source_dict['source_url']}"
                )
            else:
                print(f"Skipping duplicate source for {entity_name}")

        # --- Stage 5: upsert relationships ---
        for relationship_dict in valid_relationships:
            from_name = relationship_dict["from_entity_name"]
            to_name = relationship_dict["to_entity_name"]
            relationship_name = relationship_dict["relationship"]
            label = f"{from_name} -> {to_name} -> {relationship_name}"

            from_id = entity_name_to_id.get(
                (from_name, relationship_dict["from_entity_domain"])
            )
            to_id = entity_name_to_id.get(
                (to_name, relationship_dict["to_entity_domain"])
            )
            relationship_type_id = relationship_type_name_to_id[relationship_name]

            existing_relationship = (
                db_session.query(EntityRelations)
                .filter_by(
                    from_entity_id=from_id,
                    to_entity_id=to_id,
                    relationship_id=relationship_type_id,
                )
                .first()
            )

            if existing_relationship:
                # Same edge: count this citation only if it is new.
                existing_rel_source = (
                    db_session.query(RelationshipSource)
                    .filter_by(
                        relationship_id=existing_relationship.id,
                        source_url=relationship_dict["source_url"],
                    )
                    .first()
                )
                if not existing_rel_source:
                    existing_relationship.evidence_count += 1
                    existing_relationship.confidence = max(
                        relationship_dict["confidence"],
                        existing_relationship.confidence,
                    )
                    db_session.add(
                        RelationshipSource(
                            relationship_id=existing_relationship.id,
                            source_name=relationship_dict["source_name"],
                            source_url=relationship_dict["source_url"],
                            confidence=relationship_dict["confidence"],
                            context=relationship_dict["context"],
                            source_author=relationship_dict.get("source_author"),
                            source_title=relationship_dict.get("source_title"),
                        )
                    )
                    print(f"Strengthened relationship: {label}")
                else:
                    print(f"Already recorded this source for: {label}")
            else:
                # New edge: evidence starts at 1, the curated citation.
                new_relationship = EntityRelations(
                    from_entity_id=from_id,
                    to_entity_id=to_id,
                    relationship_id=relationship_type_id,
                    confidence=relationship_dict["confidence"],
                    context=relationship_dict["context"],
                    evidence_count=1,
                )
                db_session.add(new_relationship)
                db_session.flush()
                db_session.add(
                    RelationshipSource(
                        relationship_id=new_relationship.id,
                        source_name=relationship_dict["source_name"],
                        source_url=relationship_dict["source_url"],
                        confidence=relationship_dict["confidence"],
                        context=relationship_dict["context"],
                        source_author=relationship_dict.get("source_author"),
                        source_title=relationship_dict.get("source_title"),
                    )
                )
                print(f"Added new relationship: {label}")

        # --- Stage 6: commit everything (all-or-nothing) ---
        db_session.commit()
        print("Load complete")

    except Exception as e:
        print(f"Load failed: {e}")
        db_session.rollback()
    finally:
        db_session.close()


def run_curated_genetics_ingestion():
    print("Starting curated genetic associations load")

    raw_rows = extract()
    entities, relationships, sources = transform(raw_rows)

    if not relationships:
        print("Nothing to load: every row is missing a source or failed a check.")
        return

    db_session = SessionLocal()
    load(entities, relationships, sources, db_session)
    print("Curated genetic associations complete")
