from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.http_utils import get_with_retry
from models.entities import Entity
from models.entity_relationships import EntityRelations
from models.entity_sources import EntitySource
from models.relations_type import RelationshipTypes
from models.relationship_sources import RelationshipSource

# TARGET_INDICATORS maps WB Code -> (Human Readable Name, Relationship Type)
# Focused on filling the 48 unpopulated gaps (mortality_rate_in, reported_by, etc.)
TARGET_INDICATORS = {
    # Mortality (Filling: mortality_rate_in)
    "SH.DTH.MCLN": ("Maternal Mortality", "mortality_rate_in"),
    "SH.DTH.DEAT": ("Death Rate", "mortality_rate_in"),
    "SH.SMR.MAL": ("Malaria Mortality Rate", "mortality_rate_in"),
    
    # Systemic Indicators (Filling: measures, associated_with)
    # These now use 'measures' because reported_by is handled explicitly in the code
    "SH.XPD.CHEX.GD.ZS": ("Health Expenditure % GDP", "measures"),
    "SH.MED.PHYS": ("Physician Density", "measures"),
    "SH.XPD.HSTK": ("Government Health Expenditure", "measures"),
    
    # Epidemiology / Prevalence (Filling: prevalent_in, endemic_to, affects_population)
    "SH.POP.LIFE": ("Life Expectancy", "measures"),
    "SH.AIR.POLL": ("Air Pollution Exposure", "risk_factor_for"),
    "SH.STA.BIRTH": ("Birth Rate", "affects_population"),
    "SH.SMR.TBC": ("Tuberculosis Mortality Rate", "endemic_to"),
}


def extract_world_bank_data(indicator_code):
    all_data = []
    extract_succeeded = True
    page = 1
    while True:
        # Request JSON format, paged results for all countries
        WORLD_BANK_URL = f"https://api.worldbank.org/v2/country/all/indicator/{indicator_code}?format=json&page={page}"

        response = get_with_retry(WORLD_BANK_URL, None, context_label=indicator_code)

        if not response:
            extract_succeeded = False
            break

        data_json = response.json()
        # World bank api retuns [metadat, data_list]
        records = data_json[1]

        if not records:
            break

        all_data.extend(records)

        # Check if we have reached the lsst page
        metadata = data_json[0]
        if page >= metadata["page"]:
            break

        page += 1

    return all_data, extract_succeeded


def transform_to_entities(raw_rows, indicator_code):
    entities = []
    relationships = []
    sources = []
    added_region = set()

    # Explicit map from TARGET_INDICATORS
    INDICATOR_DATA = TARGET_INDICATORS.get(
        indicator_code, ("Unknown Health Indicator", "associated_with")
    )
    INDICATOR_NAME, REL_NAME = INDICATOR_DATA

    # 0. Institutional Entity (The Reporting Authority)
    entities.append(
        {
            "name": "World Bank",
            "domain": "institutional",
            "entity_type": "Institutional",
            "confidence": 3,
            "contributor": "World Bank",
        }
    )
    sources.append({
        "entity_name": "World Bank",
        "domain": "institutional",
        "source_name": "World Bank",
        "source_url": "https://data.worldbank.org",
    })

    for row in raw_rows:
        country_iso = row["country"]["id"]
        country_name = row["country"]["value"]
        value = row["value"]
        year = row["date"]

        source_url = f"https://data.worldbank.org/indicator/{indicator_code}"

        # 1. Disease/Topic entity
        entities.append(
            {
                "name": INDICATOR_NAME,
                "domain": "healthcare",
                "entity_type": "disease",
                "confidence": 3,
                "contributor": "World Bank",
            }
        )
        sources.append({
            "entity_name": INDICATOR_NAME,
            "domain": "healthcare",
            "source_name": "World Bank",
            "source_url": source_url,
        })

        # 2. Statistic entity
        stat_name = f"{INDICATOR_NAME} {country_iso} {year}"
        entities.append(
            {
                "name": stat_name,
                "domain": "healthcare",
                "entity_type": "prevalence_statistic",
                "region": country_iso,
                "expression": str(value),
                "confidence": 3,
                "contributor": "World Bank",
            }
        )
        sources.append({
            "entity_name": stat_name,
            "domain": "healthcare",
            "source_name": "World Bank",
            "source_url": source_url,
        })

        # 3. Region entity
        if country_iso not in added_region:
            entities.append(
                {
                    "name": country_name,
                    "domain": "geography",
                    "entity_type": "Country",
                    "region": country_iso,
                    "confidence": 3,
                    "contributor": "World Bank",
                }
            )
            sources.append({
                "entity_name": country_name,
                "domain": "geography",
                "source_name": "World Bank",
                "source_url": source_url,
            })
            added_region.add(country_iso)

        # 4. Relationships
        # Map the statistic to the Topic using the specific rel_type from map
        relationships.append(
            {
                "from_entity_name": stat_name,
                "from_entity_domain": "healthcare",
                "to_entity_name": INDICATOR_NAME,
                "to_entity_domain": "healthcare",
                "relationship_name": REL_NAME,
                "confidence": 3,
                "context": f"Year: {year}, Value: {value}",
                "source_url": source_url,
            }
        )

        # New reported_by link: Statistic -> World Bank
        relationships.append(
            {
                "from_entity_name": stat_name,
                "from_entity_domain": "healthcare",
                "to_entity_name": "World Bank",
                "to_entity_domain": "institutional",
                "relationship_name": "reported_by",
                "confidence": 3,
                "context": f"Year: {year}",
                "source_url": source_url,
            }
        )

        relationships.append(
            {
                "from_entity_name": stat_name,
                "from_entity_domain": "healthcare",
                "to_entity_name": country_name,
                "to_entity_domain": "geography",
                "relationship_name": "prevalent_in",
                "confidence": 3,
                "context": f"Year: {year}",
                "source_url": source_url,
            }
        )
    return entities, relationships, sources


def load_to_database(
    db: Session,
    entities: List[Dict[str, Any]],
    relationships: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
):
    """
    Loads entities and relationships into the database, handling uniqueness.

    Args:
        db (Session): The SQLAlchemy database session.
        entities (List[Dict[str, Any]]): List of entity dictionaries to load.
        relationships (List[Dict[str, Any]]): List of relationship dictionaries to load.
    """
    entity_name_to_id = {}
    relationship_type_name_to_id = {}

    try:
        # --- Pre-load relationship types ---
        db_relationship_types = db.query(RelationshipTypes).all()
        for rel_type_obj in db_relationship_types:
            relationship_type_name_to_id[rel_type_obj.name] = rel_type_obj.id

        # --- Upsert entities ---
        for entity_dict in entities:
            entity_name = entity_dict["name"]
            domain = entity_dict.get("domain")
            normalized_name = entity_name.lower().strip()

            existing_entity = (
                db.query(Entity)
                .filter(func.lower(func.trim(Entity.name)) == normalized_name)
                .filter_by(domain=domain)
                .first()
            )

            if existing_entity:
                if entity_dict["confidence"] > existing_entity.confidence:
                    existing_entity.confidence = entity_dict["confidence"]
                    print(f"Upgraded confidence for entity: {entity_name} ({domain})")
                entity_name_to_id[(entity_name, domain)] = existing_entity.id
            else:
                new_entity = Entity(**entity_dict, evidence_count=1)
                db.add(new_entity)
                db.flush()
                entity_name_to_id[(new_entity.name, domain)] = new_entity.id
                print(f"Added new entity: {entity_name} ({domain})")

        # --- Upsert sources, strengthening evidence_count on genuinely new evidence ---
        for source_dict in sources:
            entity_name = source_dict["entity_name"]
            domain = source_dict["domain"]
            entity_id = entity_name_to_id.get((entity_name, domain))

            if not entity_id:
                print(
                    f"Warning: Entity ID not found for source entity {entity_name} ({domain}), skipping source"
                )
                continue

            existing_source = (
                db.query(EntitySource)
                .filter_by(entity_id=entity_id, source_url=source_dict["source_url"])
                .first()
            )

            if not existing_source:
                new_source = EntitySource(
                    entity_id=entity_id,
                    source_name=source_dict["source_name"],
                    source_url=source_dict["source_url"],
                    access_at=datetime.now(timezone.utc),
                )
                db.add(new_source)

                entity = db.query(Entity).filter_by(id=entity_id).first()
                if entity:
                    entity.evidence_count += 1  # type: ignore[assignment]
                    print(
                        f"Added new source for {entity_name}: {source_dict['source_url']}"
                    )
            else:
                print(
                    f"Skipping duplicate source for {entity_name}: {source_dict['source_url']}"
                )

        # --- Upsert relationships ---
        for relationship_dict in relationships:
            from_entity_name = relationship_dict["from_entity_name"]
            from_entity_domain = relationship_dict["from_entity_domain"]
            to_entity_name = relationship_dict["to_entity_name"]
            to_entity_domain = relationship_dict["to_entity_domain"]
            relationship_name = relationship_dict["relationship_name"]

            from_entity_id = entity_name_to_id.get(
                (from_entity_name, from_entity_domain)
            )
            to_entity_id = entity_name_to_id.get((to_entity_name, to_entity_domain))
            relationship_type_id = relationship_type_name_to_id.get(relationship_name)

            if (
                from_entity_id is None
                or to_entity_id is None
                or relationship_type_id is None
            ):
                print(
                    f"Warning: Skipping relationship due to unresolved IDs: "
                    f"{from_entity_name} -> {to_entity_name} -> {relationship_name}."
                )
                continue

            existing_relationship = (
                db.query(EntityRelations)
                .filter(
                    EntityRelations.from_entity_id == from_entity_id,
                    EntityRelations.to_entity_id == to_entity_id,
                    EntityRelations.relationship_id == relationship_type_id,
                )
                .first()
            )

            if existing_relationship:
                existing_rel_source = (
                    db.query(RelationshipSource)
                    .filter_by(
                        relationship_id=existing_relationship.id,
                        source_url=relationship_dict["source_url"],
                    )
                    .first()
                )

                if not existing_rel_source:
                    existing_relationship.evidence_count += 1  # type: ignore[assignment]

                    existing_relationship.confidence = max(
                        existing_relationship.confidence,
                        relationship_dict["confidence"],
                    )

                    new_rel_source = RelationshipSource(
                        relationship_id=existing_relationship.id,
                        source_name="World Bank",
                        source_url=relationship_dict["source_url"],
                        confidence=relationship_dict["confidence"],
                        context=relationship_dict["context"],
                    )
                    db.add(new_rel_source)
                    print(
                        f"Strengthened relationship: {from_entity_name} -> "
                        f"{to_entity_name} -> {relationship_name}"
                    )
                else:
                    print(
                        f"Already recorded this source for relationship: "
                        f"{from_entity_name} -> {to_entity_name} -> {relationship_name}"
                    )

            else:
                new_relationship = EntityRelations(
                    from_entity_id=from_entity_id,
                    to_entity_id=to_entity_id,
                    relationship_id=relationship_type_id,
                    confidence=relationship_dict.get("confidence"),
                    context=relationship_dict.get("context"),
                    evidence_count=1,
                )
                db.add(new_relationship)
                db.flush()

                new_rel_source = RelationshipSource(
                    relationship_id=new_relationship.id,
                    source_name="World Bank",
                    source_url=relationship_dict["source_url"],
                    confidence=relationship_dict["confidence"],
                    context=relationship_dict["context"],
                )
                db.add(new_rel_source)
                print(
                    f"Added new relationship: {from_entity_name} -> "
                    f"{to_entity_name} -> {relationship_name}"
                )

        db.commit()
        print("Load complete")

    except Exception as e:
        print(f"An error occurred during data loading: {e}")
        db.rollback()
