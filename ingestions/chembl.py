import requests
from app.http_utils import get_with_retry
import time
import json
from typing import List, Dict, Any, Tuple
from ingestions.openalex import DISEASE_VOCABULARY, TREATMENT_VOCABULARY
CHEMBL_BASE_URL = "https://www.ebi.ac.uk/chembl/api/data/"
DRUG_INDICATION_CAP_PER_DISEASE = 1000
MECHANISM_CAP_PER_MOLECULE = 50
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
                break
            if response is None:
                print(f"API failed after retries for {disease_name} (mesh_id: {mesh_id})")
                current_page_url = None
                break
            try:
                JSON_DATA = response.json()
            except json.JSONDecodeError as e:
                print(f"Error decoding json for {disease_name} (mesh_id: {mesh_id}, URL: {current_page_url}): {e}. Response: {response.text[:200]}...")
                current_page_url = None
                break

            if response.status_code != 200 or JSON_DATA.get('drug_indications') is None:
                print(f"Error or no drug_indications found for {disease_name} (mesh_id: {mesh_id}) on page {current_page_url}")
                current_page_url = None # Stop pagination
                break
            for indication_record in JSON_DATA.get('drug_indications'):
                raw_drug_indications_data.append(indication_record)
                indications_count_for_mesh_id += 1
                if indications_count_for_mesh_id >= DRUG_INDICATION_CAP_PER_DISEASE:
                    break

            current_page_url = JSON_DATA.get('page_meta', {}).get('next') # Get next page url
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
            else:
                JSON_DATA = response.json()
                if response.status_code == 200 and JSON_DATA.get('molecule_chembl_id') is not None:
                    raw_molecules_data.append(JSON_DATA)
                else:
                    print(f"Error or no molecule details found for {molecule_chembl_id}")


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
            else:
                try:
                    JSON_DATA = response.json()
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON for mecahnism {molecule_chembl_id}: {e}. Response: {response.text[:200]}...")
                    JSON_DATA = {}

                mechanisms = JSON_DATA.get('mechanisms')
                if response.status_code == 200 and mechanisms is not None:
                    for mechanism_record in mechanisms:
                        raw_mechanisms_data.append(mechanism_record)
                        unique_target_chembl_id.add(mechanism_record.get('target_chembl_id'))
                else:
                    print(f"Error or no mechanisms found for {molecule_chembl_id}")

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
            else:
                try:
                    JSON_DATA = response.json()
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON for target {target_chembl_id}: {e}. Response: {response.text[:200]}...")
                    JSON_DATA = {}
                if response.status_code == 200 and JSON_DATA.get('target_chembl_id') is not None:
                    raw_targets_data.append(JSON_DATA)
                else:
                    print(f"Error or no target details found for {target_chembl_id}")

            time.sleep(0.1)

    return{
        "indications": raw_drug_indications_data,
        "molecules": raw_molecules_data,
        "mechanisms": raw_mechanisms_data,
        "targets": raw_targets_data
    }

# Stage 2: transform(raw_data, disease_name)
# Converts raw ChEMBL data into Sankofa entity and relationship dicts
def transform(raw_data, disease_name):
    entities = []
    relationships = []
    combined_sources = []
    added_molecules_unique_ids = set()
    added_targets_unique_ids = set()
    molecule_id_to_pref_name = {}
    target_id_to_pref_name = {}

    # Populate lookup maps for molecule and target names
    for mol_record in raw_data.get('molecules', []):
        if mol_record.get('molecule_chembl_id') is not None:
            pref_name = mol_record.get('pref_name')
            molecule_id_to_pref_name[mol_record.get('molecule_chembl_id')] = pref_name if pref_name is not None else mol_record.get('molecule_chembl_id')

    for target_record in raw_data.get('targets', []):
        if target_record.get('target_chembl_id') is not None:
            pref_name = target_record.get('pref_name')
            target_id_to_pref_name[target_record.get('target_chembl_id')] = pref_name if pref_name is not None else target_record.get('target_chembl_id')

    # Deduplicate indications: a single (molecule, disease) pair can appear multiple raw_drug_indications_data records
    deduped_indications_map = {}
    for indications_record in raw_data.get('indications', []):
        try:
            molecule_chembl_id = indications_record.get('molecule_chembl_id')
            if molecule_chembl_id is None:
                continue

            #Fix 3: max_phase_for_ind needs explicit type conversion
            max_phase_string = indications_record.get('max_phase_for_ind')
            max_phase_float = float(max_phase_string)
            # NOTE: Deliberately falls through to confidence=1 for -1.0 (unknown) and 0.5 (fractional) - intentional

            parent_molecule_chembl_id = indications_record.get('parent_molecule_chembl_id')
            current_indication_refs = indications_record.get('current_indication_refs', [])

            dedupe_key = (molecule_chembl_id, disease_name)
            if dedupe_key not in deduped_indications_map:
                deduped_indications_map[dedupe_key] = {
                    "max_phase_for_ind": 0.0, # Initialize with lowest phase
                    "parent_molecule_chembl_id": parent_molecule_chembl_id,
                    "indication_refs": []
                }

            # Merge refs and take MAX max_phase_for_ind
            for ref in current_indication_refs:
                deduped_indications_map[dedupe_key]['indication_refs'].append(ref)

            if max_phase_float > deduped_indications_map[dedupe_key]['max_phase_for_ind']:
                deduped_indications_map[dedupe_key]['max_phase_for_ind'] = max_phase_float
        except Exception as e:
            print(f"Error processing indication record for dedupe: {e}")
            continue

    # Build entities and relationships from deduped indications
    for dedupe_key, deduped_info in deduped_indications_map.items():
        try:
            molecule_chembl_id = dedupe_key[0]
            current_disease_name = dedupe_key[1]
            molecule_display_name = molecule_id_to_pref_name.get(molecule_chembl_id)

            if molecule_display_name is None:
                molecule_display_name = molecule_chembl_id # Fallback to ID if name not found

            if molecule_chembl_id not in added_molecules_unique_ids:
                molecule_entity_dict = {}
                molecule_entity_dict['type'] = MOLECULE_ENTITY_TYPE
                molecule_entity_dict['unique_id'] = molecule_chembl_id
                molecule_entity_dict['name'] = molecule_display_name
                molecule_entity_dict['properties'] = {"chembl_id": molecule_chembl_id}
                entities.append(molecule_entity_dict)
                added_molecules_unique_ids.add(molecule_chembl_id)

              # treats relationship
            treats_confidence = 1
            max_phase_value = deduped_info.get('max_phase_for_ind')
            if max_phase_value == 4.0:
                treats_confidence = 3
            elif max_phase_value >= 1.0 and max_phase_value <= 3.0:
                treats_confidence = 2


            treats_relationship_dict = {}
            treats_relationship_dict['type'] = "treats"
            treats_relationship_dict['source_id'] = molecule_chembl_id
            treats_relationship_dict['target_id'] = current_disease_name
            treats_relationship_dict['confidence'] = treats_confidence
            treats_relationship_dict['evidence_count'] = 1
            # Use a unique internal ID for relationships to link sources
            treats_relationship_dict['internal_id'] = f"treats_{molecule_chembl_id}_{current_disease_name}"
            relationships.append(treats_relationship_dict)

            # Add relationship_sources for provenance
            for ref in deduped_info.get('indication_refs', []):
                source_dict = {}
                source_dict['relationship_internal_id'] = treats_relationship_dict['internal_id']
                source_dict['source_name'] = ref.get('ref-type')
                source_dict['source_url'] = ref.get('ref_url')
                combined_sources.append(source_dict)

            # derived_form relationship if parent_molecule_chembl_id is present and different
            parent_mol_id = deduped_info.get('parent_molecule_chembl_id')
            if parent_mol_id is not None and parent_mol_id != molecule_chembl_id:
                if parent_mol_id not in added_molecules_unique_ids:
                    parent_display_name = molecule_id_to_pref_name.get(parent_mol_id)
                    if parent_display_name is None:
                        parent_display_name = parent_mol_id
                    parent_molecule_entity_dict = {}
                    parent_molecule_entity_dict['type'] = MOLECULE_ENTITY_TYPE
                    parent_molecule_entity_dict['unique_id'] = parent_mol_id
                    parent_molecule_entity_dict['name'] = parent_display_name
                    parent_molecule_entity_dict['properties'] = {"chembl": parent_mol_id}
                    entities.append(parent_molecule_entity_dict)
                    added_molecules_unique_ids.add(parent_mol_id)

                derived_from_relationship_dict = {}
                derived_from_relationship_dict['type'] = "derived_from"
                derived_from_relationship_dict['source_id'] = molecule_chembl_id
                derived_from_relationship_dict['target_id'] = parent_mol_id
                derived_from_relationship_dict['confidence'] = 3
                derived_from_relationship_dict['evidence_count'] = 1
                relationships.append(derived_from_relationship_dict)
        except Exception as error:
            print(f"Error building entities/relationships from deduped indications: {error}")
            continue

    # Mechanisms processing (targets, inhibits, binds-to)
    for mechanism_record in raw_data.get('mechanisms', []):
        try:
            mol_id = mechanism_record.get('molecule_chembl_id')
            target_id = mechanism_record.get('target_chembl_id')
            action_type = mechanism_record.get('action_type')

            if mol_id is None or target_id is None:
                continue

            target_display_name = target_id_to_pref_name.get(target_id)
            if target_display_name is None:
                target_display_name = target_id # Fallback to ID

            if target_id not in added_targets_unique_ids:
                target_entity_dict = {}
                target_entity_dict['type'] = BIOLOGICAL_ENTITY_TYPE
                target_entity_dict['unique_id'] = target_id
                target_entity_dict['name'] = target_display_name
                target_entity_dict['properties'] = {"chembl": target_id}
                entities.append(target_entity_dict)
                added_targets_unique_ids.add(target_id)

            # Always 'targets' relationship
            targets_relationship_dict = {}
            targets_relationship_dict['type'] = "targets"
            targets_relationship_dict['source_id'] = mol_id
            targets_relationship_dict['target_id'] = target_id
            targets_relationship_dict['confidence'] = 3
            targets_relationship_dict['evidence_count'] = 1
            relationships.append(targets_relationship_dict)

            if action_type == "INHIBITOR":
                inhibits_relationship_dict = {}
                inhibits_relationship_dict['type'] = "inhibits"
                inhibits_relationship_dict['source_id'] = mol_id
                inhibits_relationship_dict['target_id'] = target_id
                inhibits_relationship_dict['confidence'] = 3
                inhibits_relationship_dict['evidence_count'] = 1
                relationships.append(inhibits_relationship_dict)
            elif action_type in ["AGONIST", "ANTAGONIST", "ACTIVATOR", "BINDING AGENT", "MODULATOR"]:
                binds_to_relationship_dict = {}
                binds_to_relationship_dict['type'] = "binds_to"
                binds_to_relationship_dict['source_id'] = mol_id
                binds_to_relationship_dict['target_id'] = target_id
                binds_to_relationship_dict['confidence'] = 3
                binds_to_relationship_dict['evidence_count'] = 1
                relationships.append(binds_to_relationship_dict)
        except Exception as e:
            print(f"Error building relationships from mechanism record: {e}")
            continue
    return entities, relationships, combined_sources
