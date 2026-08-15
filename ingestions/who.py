from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.http_utils import get_with_retry
from models.entities import Entity
from models.entity_relationships import EntityRelations
from models.entity_sources import EntitySource
from models.relations_type import RelationshipTypes
from models.relationship_sources import RelationshipSource

WHO_BASE_URL = "https://ghoapi.azureedge.net/api/"
DEFAULT_PAGE_SIZE = 1000  # WHO API often uses a default page size for $top


def extract_who_data(
    indicator_code: str, country_codes: List[str]
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Extracts data for a given WHO indicator and list of country codes, handling pagination.

    Args:
        indicator_code (str): The WHO indicator code (e.g., "MALARIA_01").
        country_codes (List[str]): A list of country codes (e.g., ["NGA", "GHA"]).

    Returns:
        List[Dict[str, Any]]: A raw list of data rows from the WHO GHO API.
            Each row is a dictionary containing fields like IndicatorCode, SpatialDim, TimeDim, NumericValue, etc.
    """

    all_data = []
    skip = 0
    extract_succeeded = True

    # Construct the OData filter for country codes
    country_filter_parts = [f"SpatialDim eq '{code}'" for code in country_codes]
    country_filter_string = " or ".join(country_filter_parts)

    while True:
        params = {
            "$filter": country_filter_string,
            "$skip": skip,
            "$top": DEFAULT_PAGE_SIZE,
        }
        try:
            # Use params dictionary directly for query parameters
            response = get_with_retry(
                f"{WHO_BASE_URL}{indicator_code}", params, context_label=indicator_code
            )
            if response is None:
                print(f"Could not fetch results for {indicator_code}, skipping.")
                extract_succeeded = False
                break
            response.raise_for_status()  # Raise an exception for HTTP errors

            # Parse the JSON response
            data = response.json()
            current_page_data = data.get(
                "value", []
            )  # API returns data under "value" key

            # Add data from the current page to the overall list
            all_data.extend(current_page_data)

            # Check for pagination: if fewer rows than page size, it's the last page
            if len(current_page_data) < DEFAULT_PAGE_SIZE:
                break
            else:
                skip += DEFAULT_PAGE_SIZE  # Increment skip for the next page
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            extract_succeeded = False
            break

    return all_data, extract_succeeded


INDICATOR_MAP = {
    "MALARIA_EST_INCIDENCE": "Malaria",
    "SDGHIV": "HIV",
    "MDG_0000000020": "Tuberculosis",
    "CM_01": "Child Mortality",
    "MDG_0000000026": "Maternal Mortality",
    # "CHOLERA_TOTAL": "Cholera",
    "MDG_0000000017": "Pneumonia",
}


def transform_to_entities(
    raw_rows: List[Dict[str, Any]], indicator_code: str
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Transforms raw WHO GHO data rows into a list of entities and relationships.

    Args:
        raw_rows (List[Dict[str, Any]]): A list of raw data rows from the WHO GHO API.
        indicator_code (str): The WHO indicator code used to fetch the raw data.

    Returns:
        tuple[List[Dict[str, Any]], List[Dict[str, Any]]]: A tuple containing two lists:
            - The first list contains dictionaries representing entities.
            - The second list contains dictionaries representing relationships.
    """
    entities = []
    relationships = []
    sources = []

    unique_disease_names = set()
    added_regions = set()

    disease_name = INDICATOR_MAP.get(indicator_code, "Unknown Disease")
    statistic_description_prefix = indicator_code.replace("_", " ").title()

    for row in raw_rows:
        spatial_dim = row.get("SpatialDim")
        time_dim = row.get("TimeDim")
        numeric_value = row.get("NumericValue")

        source_url = f"{WHO_BASE_URL}{indicator_code}?SpatialDim={spatial_dim}&TimeDim={time_dim}"

        # --- 1. Disease entity (no source_url inside the entity dict) ---
        if disease_name not in unique_disease_names:
            disease_entity = {
                "name": disease_name,
                "domain": "epidemiology",
                "entity_type": "disease",
                "confidence": 3,
                "contributor": "WHO GHO",
            }
            entities.append(disease_entity)
            unique_disease_names.add(disease_name)

            sources.append(
                {
                    "entity_name": disease_name,
                    "domain": "epidemiology",
                    "source_name": "WHO GHO",
                    "source_url": source_url,
                }
            )

            # --- 2. Statistic entity ---
        statistic_entity_name = (
            f"{statistic_description_prefix} {spatial_dim} {time_dim}"
        )

        statistic_entity = {
            "name": statistic_entity_name,
            "domain": "epidemiology",
            "entity_type": "prevalence_statistic",
            "region": spatial_dim,
            "expression": str(numeric_value) if numeric_value is not None else None,
            "confidence": 3,
            "contributor": "WHO GHO",
        }
        entities.append(statistic_entity)

        sources.append(
            {
                "entity_name": statistic_entity_name,
                "domain": "epidemiology",
                "source_name": "WHO GHO",
                "source_url": source_url,
            }
        )

        # --- 3. Region entity, built here now, not inside load() ---
        if spatial_dim not in added_regions:
            region_entity = {
                "name": spatial_dim,
                "domain": "geography",
                "entity_type": "region",
                "confidence": 3,
                "contributor": "WHO GHO (implicit region)",
            }
            entities.append(region_entity)
            added_regions.add(spatial_dim)

            sources.append(
                {
                    "entity_name": spatial_dim,
                    "domain": "geography",
                    "source_name": "WHO GHO",
                    "source_url": source_url,
                }
            )

        # --- 4. Relationships ---
        relationships.append(
            {
                "from_entity_name": statistic_entity_name,
                "from_entity_domain": "epidemiology",
                "to_entity_name": disease_name,
                "to_entity_domain": "epidemiology",
                "relationship_name": "measures",
                "confidence": 3,
                "context": f"Year: {time_dim},Source: WHO GHO",
                "source_url": source_url,
            }
        )

        relationships.append(
            {
                "from_entity_name": statistic_entity_name,
                "from_entity_domain": "epidemiology",
                "to_entity_name": spatial_dim,
                "to_entity_domain": "geography",
                "relationship_name": "prevalent_in",
                "confidence": 3,
                "context": f"Year: {time_dim}, Source: WHO GHO",
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

            from_entity_id = entity_name_to_id.get((from_entity_name, from_entity_domain))
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

                    existing_relationship.confidence = max(existing_relationship.confidence, relationship_dict["confidence"])

                    new_rel_source = RelationshipSource(
                        relationship_id=existing_relationship.id,
                        source_name="WHO GHO",
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
                    source_name="WHO GHO",
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
