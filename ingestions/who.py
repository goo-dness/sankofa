from typing import Any, Dict, List

import httpx

WHO_BASE_URL = "https://ghoapi.azureedge.net/api/"
DEFAULT_PAGE_SIZE = 1000  # WHO API size often uses a default page for $top


def extract_who_data(
    indicator_code: str, country_codes: List[str]
) -> List[Dict[str, Any]]:
    """
    Extract data for a given WHO indidcator and list of country codes, handling pagination.

    Args:
        indidcator_code (str): The WHO indicator code (e.g., "MALARIA_01").
        country_code (List[str]): A list of country codes (e.g., ["NGA", "GHA"]).

        Returns:
            List[Dict[str, Any]]: A raw list of data rows from the WH GHO API.
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
            response = httpx.get(
                f"{WHO_BASE_URL}{indicator_code}", params=params, timeout=30.0
            )
            response.raise_for_status()  # Raise an exception for HTTP errors

            # Parse the JSON response
            data = response.json()
            current_page_data = data.get(
                "value", []
            )  # API returns data under value key

            # Add data from the current page to the overall list
            all_data.extend(current_page_data)

            # Check for pagination: if fewer rows than page size it`s the last page
            if len(current_page_data) < DEFAULT_PAGE_SIZE:
                break
            else:
                skip += DEFAULT_PAGE_SIZE  # Increment skip for the next page
        except httpx.HTTPStatusError as e:
            print(f"HTTP error occured while fetching data for {indicator_code}: {e}")
            print(f"Response content: {e.response.text}")
            break
        except httpx.RequestError as e:
            print(
                f"Request error occured while fetching data for {indicator_code}: {e}"
            )
            break
        except Exception as e:
            print(f"An unexpected error has occured: {e}")
            break

    return all_data


INDICATOR_MAP = {
    "MALARIA_EST_INCIDENCE": "Malaria",
    "HIV_PREV": "HIV",
    "TB_INCIDENCE": "Tuberculosis",
    "CM_01": "Child Mortality",
    "MMR": "Maternal Mortality",
    "CHOLERA_TOTAL": "Cholera",
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
               - The second list contains dictionaries representing relationships
    """
    entities = []
    relationships = []

    # Use set to check for duplicate of disease names
    unique_disease_names = set()

    # Use the INDICATOR_MAP to get the disease name, default to Unknown disease if the indicator_code is not found
    disease_name = INDICATOR_MAP.get(indicator_code, "Unknown Disease")

    # Create a human readable prefix for the statistic`s entity name by replcing underscore with space
    statistic_description_prefix = indicator_code.replace("_", " ").title()

    # Loop throug each raw data dictionary
    for row in raw_rows:
        spartial_dim = row.get("SpartialDim")
        time_dim = row.get("TimeDim")
        numeric_value = row.get("NumericValue")

        # --- 1 Create Disease Entity
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

        # --- 2 Create Statistic Entity
        statistic_entity_name = (
            f"{statistic_description_prefix} {spartial_dim} {time_dim}"
        )

        statistic_entity = {
            "name": statistic_entity_name,
            "domain": "epidemiology",
            "entity_type": "prevalence_statistics",
            "region": spartial_dim,
            "expression": str(numeric_value) if numeric_value is not None else None,
            "confidence": 3,
            "contributor": "WHO GHO",
        }
        entities.append(statistic_entity)

        # --- 3 Create Relationships
        # #Relationship 1: statistic -> measures -> disease
        relationships.append(
            {
                "from_entity_name": statistic_entity_name,
                "to_entity_name": disease_name,
                "relationship_name": "measures",
                "confidence": 3,
                "context": f"Year: {time_dim}. Source: WHO GHO",
            }
        )
        # Relationship 2: statistic -> prevalent_in -> region (SpartialDim as entity name)
        relationships.append(
            {
                "from_entity_name": statistic_entity_name,
                "to_entity_name": spartial_dim,  # country code can act as a region entity name
                "relationship_name": "prevalent_in",
                "confidence": 3,
                "context": f"Year: {time_dim}. Source: WHO GHO.",
            }
        )
    return entities, relationships
