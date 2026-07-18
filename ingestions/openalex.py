import time
from typing import Any, Dict, List, Tuple

import httpx
import requests
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.http_utils import get_with_retry
from models.entities import Entity
from models.entity_relationships import EntityRelations
from models.entity_sources import EntitySource
from models.relations_type import RelationshipTypes
from models.relationship_sources import RelationshipSource

# CONSTANTS
OPENALEX_URL = "https://api.openalex.org/works"
PER_PAGE = 50
CAP = 500
DISEASE_VOCABULARY = [
    "malaria",
    "HIV",
    "tuberculosis",
    "pneumonia",
    "cholera",
    "typhoid fever",
    "meningitis",
    "hepatitis B",
    "hepatitis C",
    "diarrhoeal disease",
    "yellow fever",
    "dengue fever",
    "ebola",
    "mpox",
    "schistosomiasis",
    "onchocerciasis",
    "lymphatic filariasis",
    "trachoma",
    "trypanosomiasis",
    "leishmaniasis",
    "buruli ulcer",
    "leprosy",
    "guinea worm",
    "soil-transmitted helminths",
    "sickle cell disease",
    "G6PD deficiency",
    "thalassaemia",
    "malnutrition",
    "neonatal sepsis",
    "obstetric fistula",
    "preeclampsia",
    "stunting",
    "lassa fever",
    "marburg virus",
    "rift valley fever",
]
TREATMENT_VOCABULARY = {
    "malaria": [
        "artemisinin",
        "chloroquine",
        "quinine",
        "coartem",
        "primaquine",
        "mefloquine",
        "artesunate",
        "lumefantrine",
        "artemether",
        "amodiaquine",
    ],
    "HIV": [
        "antiretroviral",
        "tenofovir",
        "efavirenz",
        "lamivudine",
        "dolutegravir",
        "zidovudine",
        "PrEP",
        "nevirapine",
        "lopinavir",
        "ritonavir",
        "abacavir",
        "emtricitabine",
    ],
    "tuberculosis": [
        "rifampicin",
        "isoniazid",
        "pyrazinamide",
        "ethambutol",
        "streptomycin",
        "DOTS",
        "bedaquiline",
        "linezolid",
        "moxifloxacin",
        "delamanid",
    ],
    "pneumonia": [
        "amoxicillin",
        "penicillin",
        "azithromycin",
        "cotrimoxazole",
        "oxygen therapy",
        "ceftriaxone",
        "ampicillin",
        "gentamicin",
    ],
    "cholera": [
        "oral rehydration",
        "ORS",
        "doxycycline",
        "zinc supplementation",
        "intravenous fluids",
        "tetracycline",
        "azithromycin",
    ],
    "typhoid fever": [
        "ciprofloxacin",
        "azithromycin",
        "ceftriaxone",
        "chloramphenicol",
        "ampicillin",
        "cotrimoxazole",
    ],
    "meningitis": [
        "ceftriaxone",
        "penicillin",
        "ampicillin",
        "dexamethasone",
        "vaccination",
        "chloramphenicol",
        "benzylpenicillin",
    ],
    "hepatitis B": [
        "tenofovir",
        "entecavir",
        "lamivudine",
        "interferon",
        "vaccination",
        "adefovir",
        "telbivudine",
    ],
    "hepatitis C": [
        "sofosbuvir",
        "ribavirin",
        "direct-acting antivirals",
        "DAA",
        "ledipasvir",
        "daclatasvir",
        "velpatasvir",
    ],
    "diarrhoeal disease": [
        "oral rehydration",
        "zinc",
        "ORS",
        "metronidazole",
        "cotrimoxazole",
        "ciprofloxacin",
    ],
    "yellow fever": ["vaccination", "supportive care"],
    "dengue fever": ["paracetamol", "fluid management", "supportive care"],
    "ebola": [
        "monoclonal antibodies",
        "Inmazeb",
        "Ebanga",
        "supportive care",
        "mAb114",
        "ZMapp",
    ],
    "mpox": [
        "tecovirimat",
        "JYNNEOS vaccine",
        "supportive care",
        "cidofovir",
        "brincidofovir",
    ],
    "schistosomiasis": ["praziquantel"],
    "onchocerciasis": ["ivermectin", "doxycycline"],
    "lymphatic filariasis": ["diethylcarbamazine", "ivermectin", "albendazole", "DEC"],
    "trachoma": ["azithromycin", "tetracycline", "SAFE strategy"],
    "trypanosomiasis": [
        "pentamidine",
        "suramin",
        "melarsoprol",
        "eflornithine",
        "nifurtimox",
        "fexinidazole",
    ],
    "leishmaniasis": [
        "miltefosine",
        "amphotericin",
        "pentamidine",
        "sodium stibogluconate",
        "liposomal amphotericin",
    ],
    "buruli ulcer": ["rifampicin", "clarithromycin", "streptomycin"],
    "leprosy": ["dapsone", "rifampicin", "clofazimine", "multidrug therapy", "MDT"],
    "guinea worm": ["mechanical extraction", "metronidazole"],
    "soil-transmitted helminths": [
        "albendazole",
        "mebendazole",
        "ivermectin",
        "pyrantel",
    ],
    "sickle cell disease": [
        "hydroxyurea",
        "folic acid",
        "blood transfusion",
        "bone marrow transplant",
        "penicillin prophylaxis",
        "voxelotor",
        "crizanlizumab",
        "L-glutamine",
    ],
    "G6PD deficiency": ["folic acid", "blood transfusion"],
    "thalassaemia": [
        "blood transfusion",
        "deferoxamine",
        "hydroxyurea",
        "chelation therapy",
        "bone marrow transplant",
        "deferasirox",
        "deferiprone",
    ],
    "malnutrition": [
        "RUTF",
        "therapeutic food",
        "micronutrient supplementation",
        "zinc",
        "vitamin A",
        "F-75",
        "F-100",
    ],
    "neonatal sepsis": ["ampicillin", "gentamicin", "ceftriaxone", "penicillin"],
    "obstetric fistula": ["surgical repair", "catheterization"],
    "preeclampsia": [
        "magnesium sulphate",
        "labetalol",
        "nifedipine",
        "methyldopa",
        "aspirin",
        "hydralazine",
    ],
    "stunting": [
        "zinc",
        "vitamin A",
        "micronutrient supplementation",
        "therapeutic feeding",
        "RUTF",
    ],
    "lassa fever": ["ribavirin", "supportive care"],
    "marburg virus": ["monoclonal antibodies", "supportive care"],
    "rift valley fever": ["ribavirin", "supportive care"],
}
TREATMENT_KEYWORDS = [
    "treatment",
    "clinical trial",
    "randomised",
    "randomized",
    "therapy",
    "drug",
    "intervention",
]
INDIGENOUS_KEYWORDS = [
    "traditional",
    "ethnobotanical",
    "herbal",
    "indigenous",
    "folk medicine",
    "plant extract",
]


# Openalex stores abstracts as word-to-positions mapping, I rebuild the original sentence from that mapping
def reconstruct_abstract(abstract_inverted_index: Dict[str, List]) -> str:
    if not abstract_inverted_index:
        return ""

    position_to_word = {}
    for word, positions in abstract_inverted_index.items():
        for position in positions:
            position_to_word[position] = word

    sorted_words = [position_to_word[pos] for pos in sorted(position_to_word.keys())]
    return " ".join(sorted_words)


# Citation is my proxy for scientific validation
def determine_confidence(cited_by_count: int) -> int:
    if cited_by_count >= 50:
        return 3  # Established confidence tier
    elif cited_by_count >= 10:
        return 2  # Emerging confidence tier
    else:
        return 1  # Traditional/ unverified


# Classify what kind of knowledge this paper represnets
def determine_entity_type(abstract_text: str) -> str:
    abstract_text_lower = abstract_text.lower()

    for keyword in INDIGENOUS_KEYWORDS:
        if keyword in abstract_text_lower:
            return "Indigenous"
    for keyword in TREATMENT_KEYWORDS:
        if keyword in abstract_text_lower:
            return "Clinical"
    return "Epidemiological"


# Walk the author institutions to find country code


def extract_region(authorships: List[Dict[str, Any]]) -> str:
    for authorship in authorships:
        for institution in authorship.get("institutions", []):
            # Use .get() to safely access 'continet'
            continent = institution.get("continent")
            if continent == "Africa":
                return institution.get("country_code", "AFRICA")
    return "AFRICA"  # Fallback if no specific country code found


# ---Stage 1: Fetch raw data from openalex
def extract_openalex_data(disease_name: str) -> List[Dict[str, Any]]:
    # Build the filter string OpenAlex expects
    filter_conditions = [
        f"title.search.exact:{disease_name}",
        "authorships.institutions.continent:Africa",
        "open_access.is_oa:true",
        "publication_year:>2009",
    ]
    filter_string = ",".join(filter_conditions)
    request_params = {
        "filter": filter_string,
        "per_page": PER_PAGE,
        "cursor": "*",  # Tells Openalex to start from beginning
        "api_key": "LavCfEBQRCydbMVkEPaZzR",
    }

    raw_records: List[Dict[str, Any]] = []

    while True:
        print(f"Making GET  request to {OPENALEX_URL} with params: {request_params}")
        response = get_with_retry(
            OPENALEX_URL, request_params, context_label=disease_name
        )
        if response is None:
            print(f"Could not fetch results for {disease_name}, skipping disease")
            continue
        # Raise an exception for HTTP errors
        if response.status_code != 200:
            print(
                f"Error fetching data for {disease_name}: {response.status_code} - {response.text}"
            )
            break
        # Parse the JSON response
        data = response.json()
        # API returns results under "results" key
        results = data.get("results", [])
        # Add data from current page to ovrall list
        raw_records.extend(results)

        # If the length of raw_records is greater than CAP, trim raw_records to exactly CAP items
        if len(raw_records) >= CAP:
            raw_records = raw_records[:CAP]
            break
        # Get next_cursor from response["meta"]["next_cursor"]
        next_cursor = data.get("meta", {}).get("next_cursor")
        if not next_cursor:
            break

        # Update request_params cursor to next_cursor
        request_params["cursor"] = next_cursor
        time.sleep(0.1)

    print(f"Fethed {len(raw_records)} records for {disease_name}")
    return raw_records


# ---Stage 2: Convert raw OpenAlex records into Sankofa entity dicts
def transform(
    raw_records: List[Dict[str, Any]], disease_name: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    entities: List[Dict[str, Any]] = []
    relationships: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    # Keep track of added regions to avoid duplicates in the entities list
    added_regions = set()
    for paper in raw_records:
        try:
            # Derive all fields we need
            abstract_text = reconstruct_abstract(paper.get("inverted_index", {}))
            confidence = determine_confidence(paper.get("cited_by_count", 0))

            entity_type = determine_entity_type(abstract_text)
            region = extract_region(paper.get("authorships", []))
            # Extract first author name for source attribution
            authorships = paper.get("authorships", [])
            first_author = ""
            if authorships and authorships[0].get("author", {}).get("display_name"):
                first_author = authorships[0]["author"]["display_name"]
            disease_entity_dict = {
                "name": disease_name,
                "domain": "healthcare",
                "entity_type": entity_type,
                "region": region,
                "expression": paper["title"],
                "confidence": confidence,
                "contributor": "OpenAlex",
            }
            entities.append(disease_entity_dict)
            # --- Build region entity ---
            if region not in added_regions:
                region_entity_type = "Continent" if region == "AFRICA" else "Country"
                region_entity_dict: Dict[str, Any] = {
                    "name": region,
                    "domain": "geography",
                    "entity_type": region_entity_type,
                    "region": region,
                    "expression": region,
                    "confidence": 3,
                    "contributor": "OpenAlex",
                }
                entities.append(region_entity_dict)
                added_regions.add(region)
            # Build source records
            # Papers are sources in Sankofa not entities
            source_dict = {
                "entity_name": disease_name,
                "source_name": "OpenAlex",
                "source_url": paper.get("doi") if paper.get("doi") else paper.get("id"),
                "source_author": first_author,
                "source_title": paper.get("title", ""),
            }
            # Add source_dict to sources
            sources.append(source_dict)

            # Build prevalent_in relationship
            prevalent_relationships_dict = {
                "from_entity_name": disease_name,
                "to_entity_name": region,
                "relationship": "prevalent_in",
                "confidence": confidence,
                "context": paper.get("title"),
                "source_url": paper.get("doi") if paper.get("doi") else paper.get("id"),
                "source_author": first_author,
                "source_title": paper.get("title", ""),
            }
            relationships.append(prevalent_relationships_dict)

            # check if paper mentions treatment
            found_treatments = []
            # Convert abstract-text to lower case
            abstract_text_lower = abstract_text.lower()

            for treatment in TREATMENT_VOCABULARY.get(disease_name, []):
                if treatment in abstract_text_lower:
                    found_treatments.append(treatment)

            # Build entity and relationship per found treatment
            for actual_treatment in found_treatments:
                treatment_entity_dict = {
                    "name": actual_treatment,
                    "domain": "healthcare",
                    "entity_type": "Clinical",
                    "region": region,
                    "expression": paper.get("title"),
                    "confidence": confidence,
                    "contributor": "OpenAlex",
                }
                entities.append(treatment_entity_dict)

                treats_relationship_dict = {
                    "from_entity_name": actual_treatment,
                    "to_entity_name": disease_name,
                    "relationship": "treats",
                    "confidence": confidence,
                    "context": paper.get("title"),
                    "source_url": paper.get("doi")
                    if paper.get("doi")
                    else paper.get("id"),
                    "source_author": first_author,
                    "source_title": paper.get("title", ""),
                }
                relationships.append(treats_relationship_dict)
        except Exception as e:
            paper_id = paper.get("id", "N/A")
            print(f"Warning: Skipping paper ID: {paper_id}")
            continue
    return entities, relationships, sources


# Upsert everything into PostgreSQL
def load(entities, relationships, sources, db_session):
    # THis map lets us link relationships without extra DB queries
    entity_name_to_id = {}

    try:
        # ---Step1: Pre-load all relationships types ---
        # Fetch all roles from relationship_types
        relationship_type_name_to_id = {
            rt.name: rt.id for rt in db_session.query(RelationshipTypes).all()
        }

        # Ensure "prevalent_in" and "treats" relationships types exist
        for rel_name in ["prevalent_in", "treats"]:
            if rel_name not in relationship_type_name_to_id:
                new_rel_type = RelationshipTypes(name=rel_name)
                db_session.add(new_rel_type)
                db_session.flush()
                relationship_type_name_to_id[rel_name] = new_rel_type.id
                print(f"Added new relationship type: {rel_name}")
        db_session.commit()

        # ---Stage 2: Upsert entities ---
        for entity_dict in entities:
            entity_name = entity_dict["name"]
            domain = entity_dict["domain"]

            existing_entity = (
                db_session.query(Entity)
                .filter_by(name=entity_name, domain=domain)
                .first()
            )
            # Check for duplicate, and compare
            if existing_entity:
                if entity_dict["confidence"] > existing_entity.confidence:
                    existing_entity.confidence = entity_dict["confidence"]
                    print(f"Upgrade confidence for entity: {entity_name}")
                entity_name_to_id[entity_name] = existing_entity.id

            else:
                # Create a new entity
                new_entity = Entity(**entity_dict, evidence_count=1)
                # Add the new entity to database
                db_session.add(new_entity)
                db_session.flush()  # get the new id before moving on
                entity_name_to_id[entity_name] = new_entity.id
                print(f"Added new entity: {entity_name}")

        # ---Stage 3: Upsert sources ---
        for source_dict in sources:
            entity_name = source_dict["entity_name"]
            entity_id = entity_name_to_id.get(entity_name)

            if not entity_id:
                print(
                    f"Warnig: Entity ID not found for source entity {entity_name}, skipping source."
                )
                continue

            existing_source = (
                db_session.query(EntitySource)
                .filter_by(entity_id=entity_id, source_url=source_dict["source_url"])
                .first()
            )

            if not existing_source:
                # Create new source data
                new_source = EntitySource(
                    entity_id=entity_id,
                    source_name=source_dict["source_name"],
                    source_url=source_dict["source_url"],
                    source_author=source_dict.get("source_author"),
                    source_title=source_dict.get("source_title"),
                )
                # Add to db
                db_session.add(new_source)

                entity = db_session.query(Entity).filter_by(id=entity_id).first()
                entity.evidence_count += 1
                print(
                    f"Added new source for {entity_name}: {source_dict['source_url']}"
                )
            else:
                print(
                    f"Skipping duplicate source for {entity_name}: {source_dict['source_url']}"
                )
        # ---Stae 4: Upsert Relationships---
        for relationship_dict in relationships:
            from_entity_name = relationship_dict["from_entity_name"]
            to_entity_name = relationship_dict["to_entity_name"]
            relationship_name = relationship_dict["relationship"]

            from_id = entity_name_to_id.get(from_entity_name)
            to_id = entity_name_to_id.get(to_entity_name)
            relationship_type_id = relationship_type_name_to_id.get(relationship_name)

            if not from_id or not to_id or not relationship_type_id:
                print(
                    f"Warning: Skipping relationship due to missing IDs: {from_entity_name} -> {to_entity_name} -> {relationship_name}. One or more IDs not found."
                )
                continue

                # Check for existing relationships
            existing_relationship = (
                db_session.query(EntityRelations)
                .filter_by(
                    from_entity_id=from_id,
                    to_entity_id=to_id,
                    relationship_id=relationship_type_id,
                )
                .first()
            )

            # If it eixsts skip
            if existing_relationship:
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

                    if (
                        relationship_dict["confidence"]
                        > existing_relationship.confidence
                    ):
                        existing_relationship.confidence = relationship_dict[
                            "confidence"
                        ]

                    new_rel_source = RelationshipSource(
                        relationship_id=existing_relationship.id,
                        source_name="OpenAlex",
                        source_url=relationship_dict["source_url"],
                        confidence=relationship_dict["confidence"],
                        context=relationship_dict["context"],
                        source_author=relationship_dict.get("source_author"),
                        source_title=relationship_dict.get("source_title"),
                    )
                    db_session.add(new_rel_source)
                    print(
                        f"Stengthened relationship: {from_entity_name} -> {to_entity_name} -> {relationship_name}"
                    )
                else:
                    print(
                        f"Already recorded this source for relationship: {from_entity_name} -> {to_entity_name} -> {relationship_name}"
                    )
            else:
                # If it doesn`t exist create a new one
                new_relationship = EntityRelations(
                    from_entity_id=from_id,
                    to_entity_id=to_id,
                    relationship_id=relationship_type_id,
                    confidence=relationship_dict["confidence"],
                    context=relationship_dict["context"],
                    evidence_count=1,
                )
                # Add the new relationship to the database
                db_session.add(new_relationship)
                db_session.flush()
                new_rel_source = RelationshipSource(
                    relationship_id=new_relationship.id,
                    source_name="OpenAlex",
                    source_url=relationship_dict["source_url"],
                    confidence=relationship_dict["confidence"],
                    context=relationship_dict["context"],
                    source_author=relationship_dict.get("source_author"),
                    source_title=relationship_dict.get("source_title")
                )
                db_session.add(new_rel_source)
                print(
                    f"Added new relationship: {from_entity_name} -> {to_entity_name} -> {relationship_name}"
                )

        # ---Stage 5: commit everything ---
        db_session.commit()
        print("Load complete")

    except Exception as e:
        print(f"Load failed: {e}")
        db_session.rollback()
    finally:
        db_session.close()


# ORCHESTRATOR: run_openalex_ingestion
# Calls all three stages in order for one disease
def run_openalex_ingestion(disease_name):
    print(f"Starting OpenAlex ingestion for: {disease_name}")

    raw_records = extract_openalex_data(disease_name)

    if not raw_records:
        # If no record exists abort the operation
        print(f"No records found for {disease_name}, aborting")
        return

    entities, relationships, sources = transform(raw_records, disease_name)
    if entities is None or relationships is None or sources is None:
        print(f"Error: Transform stage returned None for {disease_name}")
        return
    db_session = SessionLocal()

    try:
        load(entities, relationships, sources, db_session)
    except Exception as e:
        print(f"Error during load stage; {e}")
    finally:
        db_session.close()

    print(f"Integration complete for:  {disease_name}")
