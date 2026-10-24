# The adapters and their assigned relationship types
# fetch_uniprot_data() -> encodes, expressed_in, structurally_similar_to
# fetch_reactome_data() -> catalyzes, cleaves, produces, suppresses
# fetch_string_data() -> activates, regulates
# fetch_clinvar_data() -> mutates_to
#
# The dictionary keys:
# from_entity
# to_entity
# relationship
# context
# confidence
# contributor
# source_url
# source_title
# source_author
#
#
# For the orchestrator;
# it will follow the exact same format as openalex.py and pubmed.py.
# following the ETL format.
# and it will also use the coverage registry uisng record_coverage.
# so the transform gets all the data and pass them to load() using the key-value pairs
# define in transform()
import time

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.http_utils import get_with_retry
from models.entities import Entity
from models.entity_relationships import EntityRelations
from models.entity_sources import EntitySource
from models.relations_type import RelationshipTypes
from models.relationship_sources import RelationshipSource

UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
UNIPROT_DETAILS_URL = "https://rest.uniprot.org/uniprotkb/accessions"


def batch_fetch(identifiers, endpoint, param_name, batch_size=50):
    # Initilalize an empty list to hold all aggregate result
    all_results = []

    # devide the list of identifiers into smaller chunks of size batch_size
    for i in range(0, len(identifiers), batch_size):
        chunk = identifiers[i : i + batch_size]
        value = ",".join(chunk) if isinstance(chunk[0], str) else chunk
        response = get_with_retry(
            endpoint,
            params={param_name: value},
            context_label=f"batch {i // batch_size + 1}",
        )

        if response is None:
            print(f"Request failed for chunk starting at index {i}")
            continue
        try:
            data = response.json()
            all_results.append(data)
        except Exception as e:
            print(f"JSON parse failed for chunk {i}: {e}")
            continue
    return all_results


def fetch_uniprot(disease_name: str) -> list[dict]:
    results = []

    query = f"(cc_disease:{disease_name}) AND (reviewed:true)"
    params = {
        "query": query,
        "size": 100,
        "fields": "accession,id,protein_name,gene_names,organism_name,cc_disease,cc_subcellular_location,cc_similarity",
        "format": "json",
    }

    response = get_with_retry(
        UNIPROT_SEARCH_URL, params=params, context_label=f"uniprot:{disease_name}"
    )
    if response is None:
        return []

    try:
        data = response.json()
    except Exception:
        return []

    return results
