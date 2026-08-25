import requests
from app.http_utils import get_with_retry, resolve_next_url
import time
import json
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import SessionLocal
from models.entities import Entity
from models.entity_relationships import EntityRelations
from models.entity_sources import EntitySource
from models.relations_type import RelationshipTypes
from models.relationship_sources import RelationshipSource
from typing import List, Dict, Any, Tuple
from ingestions.openalex import DISEASE_VOCABULARY, TREATMENT_VOCABULARY, CAUSAL_AGENT_ENTITY_TYPE


CHEMBL_BASE_URL = "https://www.ebi.ac.uk/chembl/api/data/"
DRUG_INDICATION_CAP_PER_DISEASE = 1000
MECHANISM_CAP_PER_MOLECULE = 50
BATCH_CHUNK_SIZE = 50  # confirmed via curl against real API; revisit if a
                       # chunk of this size ever produces a slow/rejected request

MESH_DISEASE_MAP = {
    "malaria": ["D008288", "D016778"],
    "HIV": ["D015658"],
    "tuberculosis": ["D014397", "D014390", "D018088"],
    "pneumonia": ["D011014"],
    "cholera": [],
    "typhoid fever": ["D014435"],
    "meningitis": ["D016919"],
    "hepatitis B": ["D019694"],
    "hepatitis C": ["D006526"],
    "diarrhoeal disease": ["D003967"],
    "yellow fever": [],
    "dengue fever": ["D003715", "D019595"],
    "ebola": ["D019142"],
    "mpox": ["D045908"],
    "schistosomiasis": ["D012552", "D012553", "D012555"],
    "onchocerciasis": ["D009855", "D015827"],
    "lymphatic filariasis": ["D005368"],
    "trachoma": [],
    "trypanosomiasis": ["D014352", "D014353"],
    "leishmaniasis": ["D007896", "D016773", "D007898", "D007897"],
    "buruli ulcer": ["D054312"],
    "leprosy": ["D007918"],
    "guinea worm": [],
    "soil-transmitted helminths": ["D006373"],
    "sickle cell disease": ["D000755"],
    "G6PD deficiency": [],
    "thalassaemia": ["D013789", "D017086"],
    "malnutrition": [],
    "neonatal sepsis": ["D000071074"],
    "obstetric fistula": [],
    "preeclampsia": ["D011225"],
    "stunting": [],
    "lassa fever": ["D007835"],
    "marburg virus": ["D008379"],
    "rift valley fever": []
}
# New entity type for ChEMBL compounds
MOLECULE_ENTITY_TYPE = "Molecule"
# Reused entity type for ChEMBL targets (proteins/enzymes)
BIOLOGICAL_ENTITY_TYPE = "Biological"


def chunk_ids(id_set, chunk_size):
    """Split a set/iterable of ChEMBL IDs into fixed-size lists, dropping any
    None values that shouldn't be sent to the API. Used to batch molecule/
    target IDs into __in filter requests instead of one call per ID."""
    ids_list = [i for i in id_set if i is not None]
    for start in range(0, len(ids_list), chunk_size):
        yield ids_list[start:start + chunk_size]


def fetch_batch(endpoint, id_field_name, ids_chunk, response_key, context_label):
    """Fetch one batch of records from a ChEMBL endpoint using the __in filter,
    following pagination if a single chunk somehow returns more than one page.
    Returns (records_list, succeeded_bool)."""
    records = []
    succeeded = True
    ids_param = ",".join(ids_chunk)
    current_url = f"{CHEMBL_BASE_URL}{endpoint}.json?{id_field_name}__in={ids_param}&limit=1000"

    while current_url is not None:
        print(f"Fetching {context_label} batch ({len(ids_chunk)} ids)")
        try:
            response = get_with_retry(current_url, params=None, timeout=30.0, context_label=context_label)
        except requests.exceptions.RequestException as e:
            print(f"Error making API request for {context_label} batch: {e}")
            return records, False

        if response is None:
            print(f"API failed after retries for {context_label} batch")
            return records, False

        try:
            json_data = response.json()
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON for {context_label} batch: {e}. Response: {response.text[:200]}...")
            return records, False

        if response.status_code != 200 or json_data.get(response_key) is None:
            print(f"Error or no {response_key} found for {context_label} batch")
            return records, False

        records.extend(json_data.get(response_key))
        current_url = resolve_next_url(json_data.get('page_meta', {}).get('next'))
        time.sleep(0.2)

    return records, succeeded


# Stage 1: extract(disease_name)
# Fetches raw data from ChEMBL for a given disease
def extract(disease_name):
    raw_drug_indications_data = []
    raw_molecules_data = []
    raw_mechanisms_data = []
    raw_targets_data = []
    extract_succeeded = True

    # 1a: look up the mesh_id(s) for the disease
    mesh_ids = MESH_DISEASE_MAP.get(disease_name)
    if mesh_ids is None or len(mesh_ids) == 0:
        print(f"Skipping {disease_name}.No mesh_id found in MESH_DISEASE_MAP")
        return {
            "indications": raw_drug_indications_data,
            "molecules": raw_molecules_data,
            "mechanisms": raw_mechanisms_data,
            "targets": raw_targets_data
        }

    # 1b: Query /drug_indication filtered by mesh_id, paginated and capped
    for mesh_id in mesh_ids:
        current_page_url = f"{CHEMBL_BASE_URL}drug_indication.json?mesh_id={mesh_id}"
        indications_count_for_mesh_id = 0

        while current_page_url is not None and indications_count_for_mesh_id < DRUG_INDICATION_CAP_PER_DISEASE:
            print(f"Fetching drug_indication for {disease_name} (mesh_id: {mesh_id}) from {current_page_url}")
            try:
                response = get_with_retry(current_page_url, params=None, timeout=30.0,
                                          context_label=f"ChEMBL drug_indication for {disease_name}")
            except requests.exceptions.RequestException as e:
                print(f"Error making API request for {disease_name} (mesh_id: {mesh_id}, URL: {current_page_url}): {e}")
                current_page_url = None
                extract_succeeded = False
                break
            if response is None:
                print(f"API failed after retries for {disease_name} (mesh_id: {mesh_id})")
                current_page_url = None
                extract_succeeded = False
                break
            try:
                JSON_DATA = response.json()
            except json.JSONDecodeError as e:
                print(f"Error decoding json for {disease_name} (mesh_id: {mesh_id}, URL: {current_page_url}): {e}. "
                      f"Response: {response.text[:200]}...")
                current_page_url = None
                extract_succeeded = False
                break

            if response.status_code != 200 or JSON_DATA.get('drug_indications') is None:
                print(f"Error or no drug_indications found for {disease_name} (mesh_id: {mesh_id}) on page {current_page_url}")
                current_page_url = None  # Stop pagination
                extract_succeeded = False
                break
            for indication_record in JSON_DATA.get('drug_indications'):
                raw_drug_indications_data.append(indication_record)
                indications_count_for_mesh_id += 1
                if indications_count_for_mesh_id >= DRUG_INDICATION_CAP_PER_DISEASE:
                    break

            current_page_url = resolve_next_url(JSON_DATA.get('page_meta', {}).get('next'))  # Get next page url
            if indications_count_for_mesh_id >= DRUG_INDICATION_CAP_PER_DISEASE:
                break

            time.sleep(0.1)

    # Identify all unique molecule_chembl_ids from drug_indications
    # Ensure parent_molecule_chembl_id values are also included for fetching pref_name
    unique_molecule_chembl_ids = set()
    for record in raw_drug_indications_data:
        unique_molecule_chembl_ids.add(record.get('molecule_chembl_id'))
        parent_id = record.get('parent_molecule_chembl_id')
        if parent_id is not None:
            unique_molecule_chembl_ids.add(parent_id)

    # --- Molecules: batched via molecule_chembl_id__in instead of one call per molecule ---
    for id_chunk in chunk_ids(unique_molecule_chembl_ids, BATCH_CHUNK_SIZE):
        batch_records, batch_succeeded = fetch_batch(
            endpoint="molecule",
            id_field_name="molecule_chembl_id",
            ids_chunk=id_chunk,
            response_key="molecules",
            context_label=f"ChEMBL molecule batch for {disease_name}",
        )
        raw_molecules_data.extend(batch_records)
        if not batch_succeeded:
            extract_succeeded = False

    # --- Mechanisms: batched the same way, target IDs collected as we go ---
    unique_target_chembl_id = set()
    for id_chunk in chunk_ids(unique_molecule_chembl_ids, BATCH_CHUNK_SIZE):
        batch_records, batch_succeeded = fetch_batch(
            endpoint="mechanism",
            id_field_name="molecule_chembl_id",
            ids_chunk=id_chunk,
            response_key="mechanisms",
            context_label=f"ChEMBL mechanism batch for {disease_name}",
        )
        for mechanism_record in batch_records:
            raw_mechanisms_data.append(mechanism_record)
            target_id = mechanism_record.get('target_chembl_id')
            if target_id is not None:
                unique_target_chembl_id.add(target_id)
        if not batch_succeeded:
            extract_succeeded = False

    # --- Targets: batched via target_chembl_id__in ---
    for id_chunk in chunk_ids(unique_target_chembl_id, BATCH_CHUNK_SIZE):
        batch_records, batch_succeeded = fetch_batch(
            endpoint="target",
            id_field_name="target_chembl_id",
            ids_chunk=id_chunk,
            response_key="targets",
            context_label=f"ChEMBL target batch for {disease_name}",
        )
        raw_targets_data.extend(batch_records)
        if not batch_succeeded:
            extract_succeeded = False

    return {
        "indications": raw_drug_indications_data,
        "molecules": raw_molecules_data,
        "mechanisms": raw_mechanisms_data,
        "targets": raw_targets_data,
        "success": extract_succeeded
    }

# Stage 2: transform(raw_data, disease_name)
# Converts raw ChEMBL data into Sankofa entity and relationship dicts

def transform(raw_data, disease_name):
    entities = []
    relationships = []
    sources = []

    added_molecule_ids = set()
    added_target_ids = set()
    molecule_id_to_pref_name = {}
    target_id_to_pref_name = {}
    target_id_to_organism = {}

    # --- Lookup maps for display names ---
    for mol_record in raw_data.get("molecules", []):
        mol_id = mol_record.get("molecule_chembl_id")
        if mol_id is not None:
            molecule_id_to_pref_name[mol_id] = mol_record.get("pref_name") or mol_id

    # Build lookup maps for targets (single pass to avoid leaking variables)
    for target_record in raw_data.get("targets", []):
        target_id = target_record.get("target_chembl_id")
        if target_id is not None:
            target_id_to_pref_name[target_id] = target_record.get("pref_name") or target_id
            target_id_to_organism[target_id] = {
                "organism_name": target_record.get("organism"),
                "organism_tax_id": target_record.get("tax_id"),  # was organism_id — that field
                # doesn't exist in ChEMBL's real
                # target response (confirmed via
                # curl); tax_id is the real,
                # NCBI-standard organism identifier
            }

    # --- Disease entity (always present) ---
    disease_entity_dict = {
        "name": disease_name,
        "domain": "healthcare",
        "entity_type": "Clinical",
        "confidence": 1,
        "contributor": "ChEMBL",
    }
    entities.append(disease_entity_dict)
    sources.append({
        "entity_name": disease_name,
        "domain": "healthcare",
        "source_name": "ChEMBL",
        "source_url": f"{CHEMBL_BASE_URL}drug_indication.json",
    })

    # --- Deduplicate indications: (molecule, disease) can appear multiple times ---
    deduped_indications_map = {}
    for indication_record in raw_data.get("indications", []):
        try:
            molecule_chembl_id = indication_record.get("molecule_chembl_id")
            if molecule_chembl_id is None:
                continue

            max_phase_raw = indication_record.get("max_phase_for_ind")
            max_phase_float = -1.0 if max_phase_raw is None else float(max_phase_raw)
            parent_molecule_chembl_id = indication_record.get("parent_molecule_chembl_id")
            current_indication_refs = indication_record.get("indication_refs", [])

            dedupe_key = (molecule_chembl_id, disease_name)
            if dedupe_key not in deduped_indications_map:
                deduped_indications_map[dedupe_key] = {
                    "max_phase_for_ind": 0.0,
                    "parent_molecule_chembl_id": parent_molecule_chembl_id,
                    "indication_refs": [],
                }

            deduped_indications_map[dedupe_key]["indication_refs"].extend(current_indication_refs)
            deduped_indications_map[dedupe_key]["max_phase_for_ind"] = max(
                max_phase_float, deduped_indications_map[dedupe_key]["max_phase_for_ind"]
            )
        except Exception as e:
            print(f"Error processing indication record for dedupe: {e}")
            continue

    # --- Build molecule entities, "treats" and "derived_from" relationships ---
    for (molecule_chembl_id, current_disease_name), deduped_info in deduped_indications_map.items():
        try:
            molecule_display_name = molecule_id_to_pref_name.get(molecule_chembl_id, molecule_chembl_id)

            if molecule_chembl_id not in added_molecule_ids:
                entities.append({
                    "name": molecule_display_name,
                    "domain": "healthcare",
                    "entity_type": MOLECULE_ENTITY_TYPE,
                    "expression": molecule_chembl_id,
                    "confidence": 2,
                    "contributor": "ChEMBL",
                })
                sources.append({
                    "entity_name": molecule_display_name,
                    "domain": "healthcare",
                    "source_name": "ChEMBL",
                    "source_url": f"{CHEMBL_BASE_URL}molecule/{molecule_chembl_id}.json",
                })
                added_molecule_ids.add(molecule_chembl_id)

            max_phase_value = deduped_info.get("max_phase_for_ind")
            if max_phase_value == 4.0:
                treats_confidence = 3
            elif 1.0 <= max_phase_value <= 3.0:
                treats_confidence = 2
            else:
                treats_confidence = 1

            rel_label, rel_domain = "Treats", "pharmacology"
            refs = deduped_info.get("indication_refs", [])

            if refs:
                for ref in refs:
                    ref_url = ref.get("ref_url")
                    if ref_url is None:
                        ref_url = f"{CHEMBL_BASE_URL}drug_indication.json?ref_id={ref.get('ref_id')}"

                    relationships.append({
                        "from_entity_name": molecule_display_name,
                        "from_entity_domain": "healthcare",
                        "to_entity_name": current_disease_name,
                        "to_entity_domain": "healthcare",
                        "relationship": "treats",
                        "relationship_type_label": rel_label,
                        "relationship_type_domain": rel_domain,
                        "confidence": treats_confidence,
                        "context": f"ChEMBL max_phase_for_ind: {max_phase_value}",
                        "source_name": ref.get("ref_type", "ChEMBL"),
                        "source_url": ref_url,
                    })
            else:
                relationships.append({
                    "from_entity_name": molecule_display_name,
                    "from_entity_domain": "healthcare",
                    "to_entity_name": current_disease_name,
                    "to_entity_domain": "healthcare",
                    "relationship": "treats",
                    "relationship_type_label": rel_label,
                    "relationship_type_domain": rel_domain,
                    "confidence": treats_confidence,
                    "context": f"ChEMBL max_phase_for_ind: {max_phase_value}",
                    "source_name": "ChEMBL",
                    "source_url": f"{CHEMBL_BASE_URL}molecule/{molecule_chembl_id}.json",
                })

            # --- derived_from relationship, if parent molecule differs ---
            parent_mol_id = deduped_info.get("parent_molecule_chembl_id")
            if parent_mol_id is not None and parent_mol_id != molecule_chembl_id:
                if parent_mol_id not in added_molecule_ids:
                    parent_display_name = molecule_id_to_pref_name.get(parent_mol_id, parent_mol_id)
                    entities.append({
                        "name": parent_display_name,
                        "domain": "healthcare",
                        "entity_type": MOLECULE_ENTITY_TYPE,
                        "expression": parent_mol_id,
                        "confidence": 2,
                        "contributor": "ChEMBL",
                    })
                    sources.append({
                        "entity_name": parent_display_name,
                        "domain": "healthcare",
                        "source_name": "ChEMBL",
                        "source_url": f"{CHEMBL_BASE_URL}molecule/{parent_mol_id}.json",
                    })
                    added_molecule_ids.add(parent_mol_id)

                derived_label, derived_domain = "Derived From", "pharmacology"
                relationships.append({
                    "from_entity_name": molecule_display_name,
                    "from_entity_domain": "healthcare",
                    "to_entity_name": molecule_id_to_pref_name.get(parent_mol_id, parent_mol_id),
                    "to_entity_domain": "healthcare",
                    "relationship": "derived_from",
                    "relationship_type_label": derived_label,
                    "relationship_type_domain": derived_domain,
                    "confidence": 3,
                    "context": None,
                    "source_name": "ChEMBL",
                    "source_url": f"{CHEMBL_BASE_URL}molecule/{molecule_chembl_id}.json",
                })
        except Exception as error:
            print(f"Error building entities/relationships from deduped indications: {error}")
            continue

    # --- Mechanisms: targets, inhibits, binds_to, expressed_by ---
    for mechanism_record in raw_data.get("mechanisms", []):
        try:
            mol_id = mechanism_record.get("molecule_chembl_id")
            target_id = mechanism_record.get("target_chembl_id")
            action_type = mechanism_record.get("action_type")

            if mol_id is None or target_id is None:
                continue

            organism_info = target_id_to_organism.get(target_id, {})
            organism_name = organism_info.get("organism_name")
            organism_tax_id = organism_info.get("organism_tax_id")

            molecule_display_name = molecule_id_to_pref_name.get(mol_id, mol_id)
            target_display_name = target_id_to_pref_name.get(target_id, target_id)

            if target_id not in added_target_ids:
                entities.append({
                    "name": target_display_name,
                    "domain": "healthcare",
                    "entity_type": BIOLOGICAL_ENTITY_TYPE,
                    "expression": target_id,
                    "confidence": 2,
                    "contributor": "ChEMBL",
                })
                sources.append({
                    "entity_name": target_display_name,
                    "domain": "healthcare",
                    "source_name": "ChEMBL",
                    "source_url": f"{CHEMBL_BASE_URL}target/{target_id}.json",
                })
                added_target_ids.add(target_id)

                if organism_name:
                    entities.append({
                        "name": organism_name,
                        "domain": "healthcare",
                        "entity_type": CAUSAL_AGENT_ENTITY_TYPE,
                        "expression": organism_tax_id or organism_name,
                        "confidence": 3,
                        "contributor": "ChEMBL",
                    })
                    sources.append({
                        "entity_name": organism_name,
                        "domain": "healthcare",
                        "source_name": "ChEMBL",
                        "source_url": f"{CHEMBL_BASE_URL}target/{target_id}.json",
                    })
                    relationships.append({
                        "from_entity_name": target_display_name,
                        "from_entity_domain": "healthcare",
                        "to_entity_name": organism_name,
                        "to_entity_domain": "healthcare",
                        "relationship": "expressed_by",
                        "relationship_type_label": "Expressed By",
                        "relationship_type_domain": "CausalAgent",
                        "confidence": 3,
                        "context": None,
                        "source_name": "ChEMBL",
                        "source_url": f"{CHEMBL_BASE_URL}target/{target_id}.json",
                    })

            targets_label, targets_domain = "Targets", "pharmacology"
            relationships.append({
                "from_entity_name": molecule_display_name,
                "from_entity_domain": "healthcare",
                "to_entity_name": target_display_name,
                "to_entity_domain": "healthcare",
                "relationship": "targets",
                "relationship_type_label": targets_label,
                "relationship_type_domain": targets_domain,
                "confidence": 3,
                "context": None,
                "source_name": "ChEMBL",
                "source_url": f"{CHEMBL_BASE_URL}mechanism.json?molecule_chembl_id={mol_id}",
            })

            if action_type == "INHIBITOR":
                inhibits_label, inhibits_domain = "Inhibits", "pharmacology"
                relationships.append({
                    "from_entity_name": molecule_display_name,
                    "from_entity_domain": "healthcare",
                    "to_entity_name": target_display_name,
                    "to_entity_domain": "healthcare",
                    "relationship": "inhibits",
                    "relationship_type_label": inhibits_label,
                    "relationship_type_domain": inhibits_domain,
                    "confidence": 3,
                    "context": None,
                    "source_name": "ChEMBL",
                    "source_url": f"{CHEMBL_BASE_URL}mechanism.json?molecule_chembl_id={mol_id}",
                })
            elif action_type in ["AGONIST", "ANTAGONIST", "ACTIVATOR", "BINDING AGENT", "MODULATOR"]:
                binds_label, binds_domain = "Binds To", "molecular"
                relationships.append({
                    "from_entity_name": molecule_display_name,
                    "from_entity_domain": "healthcare",
                    "to_entity_name": target_display_name,
                    "to_entity_domain": "healthcare",
                    "relationship": "binds_to",
                    "relationship_type_label": binds_label,
                    "relationship_type_domain": binds_domain,
                    "confidence": 3,
                    "context": None,
                    "source_name": "ChEMBL",
                    "source_url": f"{CHEMBL_BASE_URL}mechanism.json?molecule_chembl_id={mol_id}",
                })
        except Exception as e:
            print(f"Error building relationships from mechanism record: {e}")
            continue

    return entities, relationships, sources

def load(entities, relationships, sources, db_session: Session):
    entity_name_domain_to_id = {}
    relationship_type_name_to_id = {}

    try:
        # --- Step 1: Pre-load relationship types, create any that are new ---
        for rt in db_session.query(RelationshipTypes).all():
            relationship_type_name_to_id[rt.name] = rt.id

        unique_relationship_type_names = set()
        for rel_dict in relationships:
            unique_relationship_type_names.add(rel_dict["relationship"])

        for rel_name in unique_relationship_type_names:
            if rel_name not in relationship_type_name_to_id:
                found_rel_info = None
                for rd in relationships:
                    if rd["relationship"] == rel_name:
                        found_rel_info = rd
                        break

                rel_label = found_rel_info.get("relationship_type_label") if found_rel_info else None
                rel_domain = found_rel_info.get("relationship_type_domain") if found_rel_info else None

                if rel_label is None or rel_domain is None:
                    print(
                        f"Warning: Skipping creation of RelationshipType '{rel_name}' - "
                        f"transform() did not supply relationship_type_label/relationship_type_domain. "
                        f"Relationships of this type will be skipped."
                    )
                    continue

                new_rel_type = RelationshipTypes(
                    name=rel_name,
                    label=rel_label,
                    domain=rel_domain,
                )
                db_session.add(new_rel_type)
                db_session.flush()
                relationship_type_name_to_id[rel_name] = new_rel_type.id
                print(f"Added new relationship type: {rel_name} (label: {rel_label}, domain: {rel_domain})")
        db_session.commit()

        # --- Step 2: Upsert entities ---
        for entity_dict in entities:
            entity_name = entity_dict["name"]
            domain = entity_dict["domain"]
            normalized_incoming_name = entity_name.lower().strip()

            existing_entity = (
                db_session.query(Entity)
                .filter(func.lower(func.trim(Entity.name)) == normalized_incoming_name)
                .filter_by(domain=domain)
                .first()
            )

            if existing_entity:
                if entity_dict["confidence"] > existing_entity.confidence:
                    existing_entity.confidence = entity_dict["confidence"]
                    print(f"Upgraded confidence for entity: {entity_name} ({domain})")
                entity_name_domain_to_id[(entity_name, domain)] = existing_entity.id
            else:
                new_entity = Entity(
                    name=entity_name,
                    domain=domain,
                    entity_type=entity_dict.get("entity_type"),
                    region=entity_dict.get("region"),
                    original_lang=entity_dict.get("original_lang"),
                    expression=entity_dict.get("expression"),
                    confidence=entity_dict["confidence"],
                    evidence_count=entity_dict.get("evidence_count", 1),
                    contributor=entity_dict.get("contributor"),
                )
                db_session.add(new_entity)
                db_session.flush()
                entity_name_domain_to_id[(entity_name, domain)] = new_entity.id
                print(f"Added new entity: {entity_name} ({domain})")
        db_session.commit()

        # --- Step 3: Upsert EntitySources ---
        for source_dict in sources:
            entity_name = source_dict["entity_name"]
            domain = source_dict["domain"]
            entity_id = entity_name_domain_to_id.get((entity_name, domain))

            if not entity_id:
                print(
                    f"Warning: Entity ID not found for source entity {entity_name} ({domain}), "
                    f"skipping source."
                )
                continue

            existing_source = (
                db_session.query(EntitySource)
                .filter_by(entity_id=entity_id, source_url=source_dict["source_url"])
                .first()
            )

            if not existing_source:
                new_source = EntitySource(
                    entity_id=entity_id,
                    source_name=source_dict["source_name"],
                    source_url=source_dict["source_url"],
                )
                db_session.add(new_source)

                entity = db_session.query(Entity).filter_by(id=entity_id).first()
                if entity:
                    entity.evidence_count = (entity.evidence_count or 0) + 1
                    print(f"Added new source for entity {entity_name} ({domain}): {source_dict['source_url']}")
            else:
                print(f"Skipping duplicate source for entity {entity_name} ({domain}): {source_dict['source_url']}")
        db_session.commit()

        # --- Step 4: Upsert EntityRelations and RelationshipSources ---
        for relationship_dict in relationships:
            from_entity_name = relationship_dict["from_entity_name"]
            from_entity_domain = relationship_dict["from_entity_domain"]
            to_entity_name = relationship_dict["to_entity_name"]
            to_entity_domain = relationship_dict["to_entity_domain"]
            relationship_name = relationship_dict["relationship"]
            source_url = relationship_dict["source_url"]
            source_name = relationship_dict["source_name"]
            confidence = relationship_dict["confidence"]
            context = relationship_dict.get("context", "")

            from_id = entity_name_domain_to_id.get((from_entity_name, from_entity_domain))
            to_id = entity_name_domain_to_id.get((to_entity_name, to_entity_domain))
            relationship_type_id = relationship_type_name_to_id.get(relationship_name)

            if not from_id or not to_id or not relationship_type_id:
                print(
                    f"Warning: Skipping relationship due to missing IDs: "
                    f"{from_entity_name} ({from_entity_domain}) -> {to_entity_name} ({to_entity_domain}) "
                    f"-> {relationship_name}."
                )
                continue

            existing_entity_relations = (
                db_session.query(EntityRelations)
                .filter_by(
                    from_entity_id=from_id,
                    to_entity_id=to_id,
                    relationship_id=relationship_type_id,
                )
                .first()
            )

            if existing_entity_relations:
                existing_rel_source = (
                    db_session.query(RelationshipSource)
                    .filter_by(
                        relationship_id=existing_entity_relations.id,
                        source_url=source_url,
                    )
                    .first()
                )
                if not existing_rel_source:
                    existing_entity_relations.evidence_count = (existing_entity_relations.evidence_count or 0) + 1
                    existing_entity_relations.confidence = max(confidence, existing_entity_relations.confidence)

                    new_rel_source = RelationshipSource(
                        relationship_id=existing_entity_relations.id,
                        source_name=source_name,
                        source_url=source_url,
                        confidence=confidence,
                        context=context,
                    )
                    db_session.add(new_rel_source)
                    print(
                        f"Strengthened relationship: {from_entity_name} -> {to_entity_name} "
                        f"({relationship_name}) from {source_url}"
                    )
                else:
                    print(
                        f"Already recorded this source for relationship: {from_entity_name} -> "
                        f"{to_entity_name} ({relationship_name}) from {source_url}"
                    )
            else:
                new_entity_relations = EntityRelations(
                    from_entity_id=from_id,
                    to_entity_id=to_id,
                    relationship_id=relationship_type_id,
                    confidence=confidence,
                    context=context,
                    evidence_count=1,
                )
                db_session.add(new_entity_relations)
                db_session.flush()

                new_rel_source = RelationshipSource(
                    relationship_id=new_entity_relations.id,
                    source_name=source_name,
                    source_url=source_url,
                    confidence=confidence,
                    context=context,
                )
                db_session.add(new_rel_source)
                print(
                    f"Added new relationship: {from_entity_name} -> {to_entity_name} "
                    f"({relationship_name}) from {source_url}"
                )

        db_session.commit()
        print("Load complete")

    except Exception as e:
        print(f"Load failed: {e}")
        db_session.rollback()
    finally:
        db_session.close()

def run_chembl_ingestion(disease_name):

    print(f"Starting ChEMBL ingestion for: {disease_name}")

    raw_data = extract(disease_name)
    extract_succeeded = raw_data.get("success", True)
    if (
        not raw_data.get("indications")
        and not raw_data.get("molecules")
        and not raw_data.get("mechanisms")
        and not raw_data.get("targets")
    ):
        if extract_succeeded:
            print(f"No records found for {disease_name}--- extraction successfully, no data exists.")
        else:
            print(f"No records found for {disease_name} --- extraction FAILED, this is not a verified absence.")
        return extract_succeeded, set()

    entities, relationships, sources = transform(raw_data, disease_name)

    db_session = SessionLocal()
    try:
        load(entities, relationships, sources, db_session)
    except Exception as e:
        print(f"Error during load stage for {disease_name}: {e}")
    finally:
        db_session.close()

    touched_relationship_types = set(r["relationship"] for r in relationships)
    print(f"ChEMBL ingestion complete for: {disease_name}")
    return extract_succeeded, touched_relationship_types
