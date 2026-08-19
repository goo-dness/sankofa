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
from ingestions.openalex import DISEASE_VOCABULARY, TREATMENT_VOCABULARY
CHEMBL_BASE_URL = "https://www.ebi.ac.uk/chembl/api/data/"
DRUG_INDICATION_CAP_PER_DISEASE = 1000
MECHANISM_CAP_PER_MOLECULE = 50
DISEASE_DOMAIN = "healthcare"
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
#New entity type for ChEMBL compounds
MOLECULE_ENTITY_TYPE = "Molecule"
#Reused entity type for ChEMBLE targets (proteins/enzymes)
BIOLOGICAL_ENTITY_TYPE = "Biological"
#Stage 1: extract(disease_name)
# Fetches raw data from ChEMBL for a given disease
def extract(disease_name):
    raw_drug_indications_data = []
    raw_molecules_data = []
    raw_mechanisms_data = []
    raw_targets_data = []
    extract_succeeded = True

    #1a: look up the mesh_id(s) for the diease
    mesh_ids = MESH_DISEASE_MAP.get(disease_name)
    if mesh_ids is None or len(mesh_ids) == 0:
        print(f"Skipping {disease_name}.No mesh_id found in MESH_DISEASE_MAP")
        return {
            "indications": raw_drug_indications_data,
            "molecules": raw_molecules_data,
            "mechanisms": raw_mechanisms_data,
            "targets": raw_targets_data
        }

    #1b: Query /drug_indication filtered by mesh_id, paginated and capped
    for mesh_id in mesh_ids:
        current_page_url = f"{CHEMBL_BASE_URL}drug_indication.json?mesh_id={mesh_id}"
        indications_count_for_mesh_id = 0

        while current_page_url is not None and indications_count_for_mesh_id < DRUG_INDICATION_CAP_PER_DISEASE:
            print(f"Fetching drug_indication for {disease_name} (mesh_id: {mesh_id}) from {current_page_url}")
            try:
                response = get_with_retry(current_page_url, params=None, timeout=30.0, context_label=f"ChEMBL drug_indication for {disease_name}")
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
                print(f"Error decoding json for {disease_name} (mesh_id: {mesh_id}, URL: {current_page_url}): {e}. Response: {response.text[:200]}...")
                current_page_url = None
                extract_succeeded = False
                break

            if response.status_code != 200 or JSON_DATA.get('drug_indications') is None:
                print(f"Error or no drug_indications found for {disease_name} (mesh_id: {mesh_id}) on page {current_page_url}")
                current_page_url = None # Stop pagination
                extract_succeeded = False
                break
            for indication_record in JSON_DATA.get('drug_indications'):
                raw_drug_indications_data.append(indication_record)
                indications_count_for_mesh_id += 1
                if indications_count_for_mesh_id >= DRUG_INDICATION_CAP_PER_DISEASE:
                    break

            current_page_url = resolve_next_url(JSON_DATA.get('page_meta', {}).get('next')) # Get next page url
            if indications_count_for_mesh_id >= DRUG_INDICATION_CAP_PER_DISEASE:
                break

            time.sleep(0.1)

    # Identify all unique molecule_chembl_ids from drug_indications
    # FIX 1: parent molecules never get their pref_name fetched (extract())
    # Ensure parent_molecule_chembl_id values are also included for fetching pref_name
    unique_molecule_chembl_ids = set()
    for record in raw_drug_indications_data:
        unique_molecule_chembl_ids.add(record.get('molecule_chembl_id'))
        parent_id = record.get('parent_molecule_chembl_id')
        if parent_id is not None:
            unique_molecule_chembl_ids.add(parent_id)

    # Identify all target_chembl_id from mechanism
    unique_target_chembl_id = set()

    # For each unique molecule_chembl_id, query /molecule and /mechanism
    for molecule_chembl_id in unique_molecule_chembl_ids:
        if molecule_chembl_id is None:
            continue

        # Query /molecule/<id> for pref_name
        molecule_url = f"{CHEMBL_BASE_URL}molecule/{molecule_chembl_id}.json"
        print(f"Fetching molecule details for {molecule_chembl_id}")
        try:
            response = get_with_retry(molecule_url, params=None, timeout=30.0, context_label=f"ChEMBL molecule details for {molecule_chembl_id}")
        except requests.exceptions.RequestException as e:
            print(f"Error making API request for {molecule_chembl_id}: {e}")
            response = None

        if response is None:
            print(f"API failed after retries for molecule {molecule_chembl_id}")
            extract_succeeded = False
        else:
            json_data = response.json()
            if response.status_code == 200 and json_data.get('molecule_chembl_id') is not None:
                raw_molecules_data.append(json_data)
            else:
                print(f"Error or no molecule details found for {molecule_chembl_id}")
                extract_succeeded = False


        # Query /mechanism?molecule_chembl_id=<id>, capped at N per molecule
        mechanism_url =f"{CHEMBL_BASE_URL}mechanism.json?molecule_chembl_id={molecule_chembl_id}"
        print(f"Fetching mechanisms for {molecule_chembl_id}")
        full_mechanism_url = f"{mechanism_url}&limit={MECHANISM_CAP_PER_MOLECULE}"
        try:
            response = get_with_retry(full_mechanism_url, params=None, timeout=30.0, context_label=f"ChEMBL mechanism for molecule {molecule_chembl_id}")
        except requests.exceptions.RequestException as e:
            print(f"Error making API request for mechanism {molecule_chembl_id}: {e}")
            response = None

        if response is None:
            print(f"API failed after retries for mechanism {molecule_chembl_id}")
            extract_succeeded = False
        else:
            try:
                json_data = response.json()
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON for mecahnism {molecule_chembl_id}: {e}. Response: {response.text[:200]}...")
                json_data = {}

            mechanisms = json_data.get('mechanisms')
            if response.status_code == 200 and mechanisms is not None:
                for mechanism_record in mechanisms:
                    raw_mechanisms_data.append(mechanism_record)
                    unique_target_chembl_id.add(mechanism_record.get('target_chembl_id'))
            else:
                print(f"Error or no mechanisms found for {molecule_chembl_id}")
                extract_succeeded = False

        time.sleep(0.1)

    # Query /target/<target_chembl_id> for pref_name (target display name)
    for target_chembl_id in unique_target_chembl_id:
        if target_chembl_id is None:
            continue

        target_url = f"{CHEMBL_BASE_URL}target/{target_chembl_id}.json"
        print(f"Fetching target details for {target_chembl_id}")
        try:
            response = get_with_retry(target_url, params=None, timeout=30.0, context_label=f"ChEMBL target for molecule {target_chembl_id}")
        except requests.exceptions.RequestException as e:
            print(f"Error making API request for target {target_chembl_id}: {e}")
            response = None

        if response is None:
            print(f"API failed after retries for target {target_chembl_id}")
            extract_succeeded = False
        else:
            try:
                json_data = response.json()
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON for target {target_chembl_id}: {e}. Response: {response.text[:200]}...")
                json_data = {}
            if response.status_code == 200 and json_data.get('target_chembl_id') is not None:
                raw_targets_data.append(json_data)
            else:
                print(f"Error or no target details found for {target_chembl_id}")
                extract_succeeded = False

        time.sleep(0.1)

    return{
        "indications": raw_drug_indications_data,
        "molecules": raw_molecules_data,
        "mechanisms": raw_mechanisms_data,
        "targets": raw_targets_data,
        "success": extract_succeeded
    }

# Stage 2: transform(raw_data, disease_name)
# Converts raw ChEMBL data into Sankofa entity and relationship dicts


# NOTE: no RELATIONSHIP_TYPE_INFO here. All five ChEMBL relationship types
# (treats, derived_from, targets, inhibits, binds_to) are already seeded in
# relationship_types via data/relationship_types.py - load()'s GET_OR_CREATE
# will find them by name and never hit the create-branch that needs label/domain.
# relationship_type_label/relationship_type_domain are still attached to each
# relationship_dict below as a defensive fallback (only used if load() ever
# encounters a genuinely new, unseeded type), but the values aren't duplicated
# from the seed file here - keeping data/relationship_types.py the single
# source of truth.


def transform(raw_data, disease_name):
    entities = []
    relationships = []
    sources = []

    added_molecule_ids = set()
    added_target_ids = set()
    molecule_id_to_pref_name = {}
    target_id_to_pref_name = {}

    # --- Lookup maps for display names ---
    for mol_record in raw_data.get("molecules", []):
        mol_id = mol_record.get("molecule_chembl_id")
        if mol_id is not None:
            molecule_id_to_pref_name[mol_id] = mol_record.get("pref_name") or mol_id

    for target_record in raw_data.get("targets", []):
        target_id = target_record.get("target_chembl_id")
        if target_id is not None:
            target_id_to_pref_name[target_id] = target_record.get("pref_name") or target_id

    # --- Disease entity: must be emitted every run, even though WHO/OpenAlex/PubMed
    # likely already created it, so load()'s Stage 2 upsert resolves its ID into the
    # entity_name_domain_to_id map for this run. Without this, every "treats"
    # relationship's to_entity lookup fails silently.
    # entity_type/confidence here only matter if this is genuinely the first pipeline
    # to create this disease - defaulting to "Clinical" / confidence 1 as a
    # placeholder since entity_type isn't part of the dedup key. Worth confirming.
    disease_entity_dict = {
        "name": disease_name,
        "domain": DISEASE_DOMAIN,
        "entity_type": "Clinical",
        "confidence": 1,
        "contributor": "ChEMBL",
    }
    entities.append(disease_entity_dict)
    sources.append({
        "entity_name": disease_name,
        "domain": DISEASE_DOMAIN,
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
            if max_phase_raw is None:
                max_phase_float = -1.0
            else:
                max_phase_float = float(max_phase_raw)
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
                    "domain": DISEASE_DOMAIN,
                    "entity_type": MOLECULE_ENTITY_TYPE,
                    "expression": molecule_chembl_id,
                    "confidence": 2,  # placeholder - ChEMBL has no per-entity confidence
                                      # signal the way OpenAlex citations or PubMed pub-types
                                      # do; worth revisiting
                    "contributor": "ChEMBL",
                })
                sources.append({
                    "entity_name": molecule_display_name,
                    "domain": DISEASE_DOMAIN,
                    "source_name": "ChEMBL",
                    "source_url": f"{CHEMBL_BASE_URL}molecule/{molecule_chembl_id}.json",
                })
                added_molecule_ids.add(molecule_chembl_id)

            # confidence tier from max_phase (clinical trial phase)
            max_phase_value = deduped_info.get("max_phase_for_ind")
            if max_phase_value == 4.0:
                treats_confidence = 3
            elif 1.0 <= max_phase_value <= 3.0:
                treats_confidence = 2
            else:
                treats_confidence = 1  # covers -1.0 (unknown) and 0.5 (fractional)

            rel_label, rel_domain = "Treats", "pharmacology"  # from relationship_types.py
            refs = deduped_info.get("indication_refs", [])

            if refs:
                # One relationship_dict per source ref - matches the established
                # one-dict-per-source-instance pattern from openalex.py/pubmed.py
                for ref in refs:
                    ref_url = ref.get("ref_url")
                    if ref_url is None:
                        ref_url = f"{CHEMBL_BASE_URL}drug_indication.json?ref_id={ref.get('ref_id')}"

                    relationships.append({
                        "from_entity_name": molecule_display_name,
                        "from_entity_domain": DISEASE_DOMAIN,
                        "to_entity_name": current_disease_name,
                        "to_entity_domain": DISEASE_DOMAIN,
                        "relationship": "treats",
                        "relationship_type_label": rel_label,
                        "relationship_type_domain": rel_domain,
                        "confidence": treats_confidence,
                        "context": f"ChEMBL max_phase_for_ind: {max_phase_value}",
                        "source_name": ref.get("ref_type", "ChEMBL"),
                        "source_url": ref_url,
                    })
            else:
                # No refs available - fall back to a ChEMBL-page source so the
                # relationship still has provenance
                relationships.append({
                    "from_entity_name": molecule_display_name,
                    "from_entity_domain": DISEASE_DOMAIN,
                    "to_entity_name": current_disease_name,
                    "to_entity_domain": DISEASE_DOMAIN,
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
                        "domain": DISEASE_DOMAIN,
                        "entity_type": MOLECULE_ENTITY_TYPE,
                        "expression": parent_mol_id,
                        "confidence": 2,
                        "contributor": "ChEMBL",
                    })
                    sources.append({
                        "entity_name": parent_display_name,
                        "domain": DISEASE_DOMAIN,
                        "source_name": "ChEMBL",
                        "source_url": f"{CHEMBL_BASE_URL}molecule/{parent_mol_id}.json",
                    })
                    added_molecule_ids.add(parent_mol_id)

                derived_label, derived_domain = "Derived From", "pharmacology"  # from relationship_types.py
                relationships.append({
                    "from_entity_name": molecule_display_name,
                    "from_entity_domain": DISEASE_DOMAIN,
                    "to_entity_name": molecule_id_to_pref_name.get(parent_mol_id, parent_mol_id),
                    "to_entity_domain": DISEASE_DOMAIN,
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

    # --- Mechanisms: targets, inhibits, binds_to ---
    for mechanism_record in raw_data.get("mechanisms", []):
        try:
            mol_id = mechanism_record.get("molecule_chembl_id")
            target_id = mechanism_record.get("target_chembl_id")
            action_type = mechanism_record.get("action_type")

            if mol_id is None or target_id is None:
                continue

            molecule_display_name = molecule_id_to_pref_name.get(mol_id, mol_id)
            target_display_name = target_id_to_pref_name.get(target_id, target_id)

            if target_id not in added_target_ids:
                entities.append({
                    "name": target_display_name,
                    "domain": DISEASE_DOMAIN,
                    "entity_type": BIOLOGICAL_ENTITY_TYPE,
                    "expression": target_id,
                    "confidence": 2,
                    "contributor": "ChEMBL",
                })
                sources.append({
                    "entity_name": target_display_name,
                    "domain": DISEASE_DOMAIN,
                    "source_name": "ChEMBL",
                    "source_url": f"{CHEMBL_BASE_URL}target/{target_id}.json",
                })
                added_target_ids.add(target_id)

            targets_label, targets_domain = "Targets", "pharmacology"  # from relationship_types.py
            relationships.append({
                "from_entity_name": molecule_display_name,
                "from_entity_domain": DISEASE_DOMAIN,
                "to_entity_name": target_display_name,
                "to_entity_domain": DISEASE_DOMAIN,
                "relationship": "targets",
                "relationship_type_label": targets_label,
                "relationship_type_domain": targets_domain,
                "confidence": 3,
                "context": None,
                "source_name": "ChEMBL",
                "source_url": f"{CHEMBL_BASE_URL}mechanism.json?molecule_chembl_id={mol_id}",
            })

            if action_type == "INHIBITOR":
                inhibits_label, inhibits_domain = "Inhibits", "pharmacology"  # from relationship_types.py
                relationships.append({
                    "from_entity_name": molecule_display_name,
                    "from_entity_domain": DISEASE_DOMAIN,
                    "to_entity_name": target_display_name,
                    "to_entity_domain": DISEASE_DOMAIN,
                    "relationship": "inhibits",
                    "relationship_type_label": inhibits_label,
                    "relationship_type_domain": inhibits_domain,
                    "confidence": 3,
                    "context": None,
                    "source_name": "ChEMBL",
                    "source_url": f"{CHEMBL_BASE_URL}mechanism.json?molecule_chembl_id={mol_id}",
                })
            elif action_type in ["AGONIST", "ANTAGONIST", "ACTIVATOR", "BINDING AGENT", "MODULATOR"]:
                binds_label, binds_domain = "Binds To", "molecular"  # from relationship_types.py
                relationships.append({
                    "from_entity_name": molecule_display_name,
                    "from_entity_domain": DISEASE_DOMAIN,
                    "to_entity_name": target_display_name,
                    "to_entity_domain": DISEASE_DOMAIN,
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
                # Find one relationship_dict carrying this type, to pull label/domain from
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
        # Dedup key: normalized (lowercased, trimmed) name + domain — entity_type deliberately
        # excluded, since the same disease/drug can carry different entity_type values across
        # OpenAlex/PubMed/ChEMBL and including it would fragment evidence_count.
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


# extract, transform, load are expected to live in this same file
# (ingestions/chembl.py) once combined - imported here only because this was
# drafted as a separate file for review.
# from ingestions.chembl import extract, transform, load


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
