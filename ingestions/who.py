from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from sqlalchemy.orm import Session

# Corrected model imports based on your project structure
from models.entities import Entity
from models.entity_relationships import EntityRelations
from models.entity_sources import EntitySource
from models.relations_type import RelationshipTypes

WHO_BASE_URL = "https://ghoapi.azureedge.net/api/"
DEFAULT_PAGE_SIZE = 1000  # WHO API often uses a default page size for $top


def extract_who_data(
    indicator_code: str, country_codes: List[str]
) -> List[Dict[str, Any]]:
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
            response = httpx.get(
                f"{WHO_BASE_URL}{indicator_code}", params=params, timeout=30.0
            )
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
        except httpx.HTTPStatusError as e:
            print(f"HTTP error occurred while fetching data for {indicator_code}: {e}")
            print(f"Response content: {e.response.text}")
            break
        except httpx.RequestError as e:
            print(
                f"Request error occurred while fetching data for {indicator_code}: {e}"
            )
            break
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            break

    return all_data


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
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
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

    # Use set to check for duplicate disease names
    unique_disease_names = set()

    # Use the INDICATOR_MAP to get the disease name, default to Unknown Disease if the indicator_code is not found
    disease_name = INDICATOR_MAP.get(indicator_code, "Unknown Disease")

    # Create a human readable prefix for the statistic's entity name by replacing underscore with space
    statistic_description_prefix = indicator_code.replace("_", " ").title()

    # Loop through each raw data dictionary
    for row in raw_rows:
        spatial_dim = row.get("SpatialDim")
        time_dim = row.get("TimeDim")
        numeric_value = row.get("NumericValue")

        # --- 1. Create Disease Entity ---
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

        # --- 2. Create Statistic Entity ---
        statistic_entity_name = (
            f"{statistic_description_prefix} {spatial_dim} {time_dim}"
        )

        statistic_entity = {
            "name": statistic_entity_name,
            "domain": "epidemiology",
            "entity_type": "prevalence_statistic",  # Corrected typo from statistics
            "region": spatial_dim,
            "expression": str(numeric_value) if numeric_value is not None else None,
            "confidence": 3,
            "contributor": "WHO GHO",
        }
        entities.append(statistic_entity)

        # --- 3. Create Relationships ---
        # Relationship 1: statistic -> measures -> disease
        relationships.append(
            {
                "from_entity_name": statistic_entity_name,
                "to_entity_name": disease_name,
                "relationship_name": "measures",
                "confidence": 3,
                "context": f"Year: {time_dim}, Source: WHO GHO",  # Consistent context string
            }
        )
        # Relationship 2: statistic -> prevalent_in -> region (SpatialDim as entity name)
        relationships.append(
            {
                "from_entity_name": statistic_entity_name,
                "to_entity_name": spatial_dim,  # Country code can act as a region entity name
                "relationship_name": "prevalent_in",
                "confidence": 3,
                "context": f"Year: {time_dim}, Source: WHO GHO",  # Consistent context string
            }
        )
    return entities, relationships


def load_to_database(
    db: Session, entities: List[Dict[str, Any]], relationships: List[Dict[str, Any]]
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
        # --- Pre-load Relationship Types ---
        db_relationship_types = db.query(RelationshipTypes).all()
        for rel_type_obj in db_relationship_types:  # Renamed loop variable
            relationship_type_name_to_id[rel_type_obj.name] = rel_type_obj.id

        if "measures" not in relationship_type_name_to_id:
            print(
                "Warning: 'measures' relationship type not found in database. Please seed your relationship_types table."
            )
        if (
            "prevalent_in" not in relationship_type_name_to_id
        ):  # Check for prevalent_in too
            print(
                "Warning: 'prevalent_in' relationship type not found in database. Please seed your relationship_types table."
            )

        # --- Process Explicit Entities (Disease, Statistic) & Their Sources ---
        for entity_dict in entities:
            entity_name = entity_dict["name"]
            # Check if the entity already exists in the database
            existing_entity = (
                db.query(Entity).filter(Entity.name == entity_name).first()
            )

            if existing_entity:
                entity_name_to_id[entity_name] = (
                    existing_entity.id
                )  # Use entity_name for consistency
            else:
                new_entity = Entity(**entity_dict)
                db.add(new_entity)
                db.flush()  # Get ID for new_entity before creating source
                entity_name_to_id[new_entity.name] = new_entity.id

                # Create EntitySource for this NEW Disease/Statistic entity
                new_source = EntitySource(
                    entity_id=new_entity.id,
                    source_name="WHO GHO",
                    source_url=WHO_BASE_URL,
                    access_at=datetime.now(timezone.utc),
                )
                db.add(new_source)

        # --- Resolve & Create Implicit Region Entities & Their Sources ---
        # This MUST happen after explicit entities, but before relationships, to ensure region IDs exist.
        for (
            relationship_dict_candidate
        ) in relationships:  # Iterate through relationships to find implicit regions
            if relationship_dict_candidate["relationship_name"] == "prevalent_in":
                region_name = relationship_dict_candidate["to_entity_name"]

                if (
                    region_name not in entity_name_to_id
                ):  # Check if it's already an explicit entity
                    # Check if region entity already exists in database (name and entity_type="region")
                    existing_region = (
                        db.query(Entity)
                        .filter(
                            Entity.name == region_name, Entity.entity_type == "region"
                        )
                        .first()
                    )

                    if existing_region:
                        entity_name_to_id[region_name] = existing_region.id
                    else:
                        new_region = Entity(
                            name=region_name,
                            domain="geography",
                            entity_type="region",
                            confidence=3,
                            contributor="WHO GHO (implicit region)",
                        )
                        db.add(new_region)
                        db.flush()  # Get ID for new_region_entity before creating source
                        entity_name_to_id[new_region.name] = new_region.id

                        # Create EntitySource for this NEW Region entity
                        new_region_source = EntitySource(
                            entity_id=new_region.id,
                            source_name="WHO GHO",
                            source_url=WHO_BASE_URL,
                            access_at=datetime.now(timezone.utc),
                        )
                        db.add(new_region_source)

        # --- Process ALL Relationships ---
        for relationship_dict in relationships:
            from_entity_name = relationship_dict["from_entity_name"]
            to_entity_name = relationship_dict["to_entity_name"]
            relationship_name = relationship_dict["relationship_name"]

            # Resolve the actual database IDs using the mappings
            from_entity_id = entity_name_to_id.get(from_entity_name)
            to_entity_id = entity_name_to_id.get(to_entity_name)
            relationship_type_id = relationship_type_name_to_id.get(relationship_name)

            # Validate that all required IDs were found
            if (
                from_entity_id is None
                or to_entity_id is None
                or relationship_type_id is None
            ):
                print(
                    f"Warning: Skipping relationship due to unresolved entity or relationship type ID: {relationship_dict}"
                )
                continue  # Skip to the next relationship

            # Check if the exact relationship already exists in the database
            existing_relationship = (  # Renamed variable for clarity
                db.query(EntityRelations)
                .filter(
                    EntityRelations.from_entity_id == from_entity_id,
                    EntityRelations.to_entity_id == to_entity_id,
                    EntityRelations.relationship_id == relationship_type_id,
                )
                .first()
            )

            if existing_relationship:
                print(
                    f"Debug: Skipping duplicate relationship: {relationship_dict}"
                )  # Changed to Debug message
            else:
                # Relationship does not exist, create new relationship
                new_relationship = EntityRelations(
                    from_entity_id=from_entity_id,
                    to_entity_id=to_entity_id,
                    relationship_id=relationship_type_id,
                    confidence=relationship_dict.get(
                        "confidence", 3
                    ),  # Use 3 as default confidence
                    context=relationship_dict.get("context"),
                )
                db.add(new_relationship)

        db.commit()  # Final commit for all operations in this try block

    except Exception as e:
        print(f"An error occurred during data loading: {e}")
        db.rollback()
