import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from app.config import settings
import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.http_utils import get_with_retry
from ingestions.openalex import (
    DISEASE_VOCABULARY,
    TREATMENT_VOCABULARY,
    determine_entity_type,
)
from models.entities import Entity
from models.entity_relationships import EntityRelations
from models.entity_sources import EntitySource
from models.relations_type import RelationshipTypes
from models.relationship_sources import RelationshipSource

PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
RETMAX = 50
PUBMED_CAP = 500
EFETCH_BATCH_SIZE = 200
MAILTO = settings.PUBMED_EMAIL

AFRICAN_COUNTRY_NAMES = [
    "Algeria",
    "Angola",
    "Benin",
    "Botswana",
    "Burkina Faso",
    "Burundi",
    "Cabo Verde",
    "Cameroon",
    "Central African Republic",
    "Chad",
    "Comoros",
    "Congo",
    "Cote d'Ivoire",
    "Democratic Republic of the Congo",
    "Djibouti",
    "Egypt",
    "Equatorial Guinea",
    "Eritrea",
    "Eswatini",
    "Ethiopia",
    "Gabon",
    "Gambia",
    "Ghana",
    "Guinea",
    "Guinea-Bissau",
    "Kenya",
    "Lesotho",
    "Liberia",
    "Libya",
    "Madagascar",
    "Malawi",
    "Mali",
    "Mauritania",
    "Mauritius",
    "Morocco",
    "Mozambique",
    "Namibia",
    "Niger",
    "Nigeria",
    "Rwanda",
    "Sao Tome and Principe",
    "Senegal",
    "Seychelles",
    "Sierra Leone",
    "Somalia",
    "South Africa",
    "South Sudan",
    "Sudan",
    "Tanzania",
    "Togo",
    "Tunisia",
    "Uganda",
    "Zambia",
    "Zimbabwe",
]
# Sort AFRICAN_COUNTRY_NAMES by length, longest first, once at module load time
LENGTH_SORTED_AFRICAN_COUNTRY_NAMES = sorted(
    AFRICAN_COUNTRY_NAMES, key=len, reverse=True
)


# Attempts to classify the disease using MeshHeadingList, keywordList, or title/abstract
def parse_pubmed_disease_terms(
    paper_xml_record: ET.Element, target_disease_name: str
) -> str:
    target_disease_name_lower = target_disease_name.lower()

    # Check MeshHeadingList first
    mesh_head_list = paper_xml_record.find("MeshHeadingList")
    if mesh_head_list is not None:
        for mesh_heading in mesh_head_list.findall("MeshHeading"):
            descriptor_element = mesh_heading.find("DescriptorName")
            if descriptor_element is not None and descriptor_element.text is not None:
                descriptor_name_text = descriptor_element.text
                descriptor_name_text = descriptor_element.text.lower()
                if target_disease_name_lower in descriptor_name_text:
                    return target_disease_name

    # Check KeyWordList with Owner="NOTNLM" if not found in MesH
    keywordlist_elements = paper_xml_record.findall(
        ".//KeywordList"
    )  # search all KeyWordLists
    for keywordlist in keywordlist_elements:
        if (
            keywordlist.attrib.get("Owner") == "NOTNLM"
        ):  # check for exact attribute match
            for keyword in keywordlist.findall("Keyword"):
                if keyword.text is not None:
                    keyword_text = keyword.text.lower()
                    if target_disease_name_lower in keyword_text:
                        return target_disease_name

    # Fallback to Title and Abstract if not found
    articletitle_element = paper_xml_record.find(
        ".//ArticleTitle"
    )  # Search all ArticleTtitle
    articletitle_text = (
        articletitle_element.text.lower()
        if articletitle_element is not None and articletitle_element.text is not None
        else ""
    )
    concatenated_abstract = []

    abstract_element = paper_xml_record.find(
        ".//Abstract"
    )  # Find the main Abstract element
    if abstract_element is not None:
        abstract_text_elements = abstract_element.findall(
            "AbstractText"
        )  # Find all AbstractText section
        for abs_text_elem in abstract_text_elements:
            if abs_text_elem.text is not None:
                concatenated_abstract.append(abs_text_elem.text)

    full_abstract_text = " ".join(concatenated_abstract).lower()
    if (
        target_disease_name_lower in articletitle_text
        or target_disease_name_lower in full_abstract_text
    ):
        return target_disease_name  # Found in title or abstract
    else:
        return "Unknown"  # Target disease not explicitly found by classification rules


# HELPER FUNCTION: determine_pubmed_confidence(pub_type_list)
# Determine confidence tier based on publication type
def determine_pubmed_confidence(publication_type_list):
    for pub_type_element in publication_type_list:
        pub_type_text = pub_type_element.text
        if pub_type_text is None:
            continue
        if (
            pub_type_text == "Randomized Controlled Trial"
            or pub_type_text == "Meta-Analysis"
            or pub_type_text == "Systematic Review"
        ):
            return 3  # Established

    for pub_type_element in publication_type_list:
        pub_type_text = pub_type_element.text
        if pub_type_text is None:
            continue
        if (
            pub_type_text == "Review"
            or pub_type_text == "Clinical Trial"
            or pub_type_text == "Observational Study"
            or pub_type_text == "Comparative Study"
        ):
            return 2  # Emerging

    return 1  # Traditionla, unclassified


# HELPER FUNCTION: extract_pubmed_region(author_list)
# Scans author affiliations for an African country name using SORTED_AFRICAN_COUNTRY_NAMES
def extract_pubmed_region(author_list):
    for author_element in author_list:
        affiliationinfo_list = author_element.findall(".//AffiliationInfo")
        if affiliationinfo_list is not None:
            for affiliationinfo in affiliationinfo_list:
                affiliation_text_element = affiliationinfo.find("Affiliation")
                if (
                    affiliation_text_element is not None
                    and affiliation_text_element.text is not None
                ):
                    affiliation_text_content = affiliation_text_element.text.lower()

                    # Critical: Scan against length-sorted country names (longest first)
                    for country_name in LENGTH_SORTED_AFRICAN_COUNTRY_NAMES:
                        country_name_lower = country_name.lower()

                        if country_name_lower in affiliation_text_content:
                            return country_name
    return "AFRICA"  # Fallback if no specific African country found


# STAGE 1: extract(disease_name)
# Fetch raw papers (PMID list then full XML) from pubmed for one disease
def extract(disease_name: str) -> Tuple[List[ET.Element], bool]:
    country_filters_list = []
    for country_name in LENGTH_SORTED_AFRICAN_COUNTRY_NAMES:
        country_filters_list.append(f"{country_name}[Affiliation]")

    country_filter_string = " OR ".join(country_filters_list)
    country_filter_string = f"({country_filter_string})"

    search_term = f"{disease_name} AND {country_filter_string}"

    request_params_esearch = {
        "db": "pubmed",
        "term": search_term,
        "retmax": RETMAX,
        "retmode": "json",
        "email": MAILTO,
    }

    all_pmids = []
    offset = 0
    extract_succeeded = True

    # Pagination loop for Esearch to get PMIDS
    while True:
        print(f"Esearch request for {disease_name} with retstart={offset}")
        request_params_esearch["retstart"] = offset
        try:
            response = get_with_retry(
                PUBMED_ESEARCH_URL,
                request_params_esearch,
                context_label=f"{disease_name} (Esearch)",
            )
            if response is None:
                print(
                    f"Could not fetch Esearch results for {disease_name}, aborting this disease"
                )
                extract_succeeded = False
                break
            JSON_DATA = response.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            print(f"Error making Esearch request for {disease_name}: {e}")
            extract_succeeded = False
            break

        if response.status_code != 200:
            print(
                f"Error fetching PMIDs for {disease_name}: {response.status_code} - {response.text}"
            )
            extract_succeeded = False
            break

        pmid_list = JSON_DATA.get("esearchresult", {}).get("idlist", [])
        all_pmids.extend(pmid_list)

        if len(all_pmids) >= PUBMED_CAP:
            all_pmids = all_pmids[:PUBMED_CAP]  # Trim to cap
            print(
                f"Reached PUBMED_CAP for {disease_name}, fetching {len(all_pmids)} PMIDs."
            )
            break

        total_available = int(JSON_DATA.get("esearchresult", {}).get("count", "0"))
        if offset + RETMAX >= total_available:
            print(f"End of avsailable PMIDs for {disease_name}.")
            break
        if len(pmid_list) == 0:
            print(f"No new PMIDs found in this page for {disease_name}.")
            break
        offset += RETMAX
        time.sleep(0.1)

    print(f"Fetched {len(all_pmids)} total PMIDs for {disease_name}")

    if len(all_pmids) == 0:
        return [], extract_succeeded

    # Batch Efetch for full XML records
    raw_pubmed_records = []
    pmid_batch_size = 200
    pmid_batches = [
        all_pmids[i : i + pmid_batch_size]
        for i in range(0, len(all_pmids), pmid_batch_size)
    ]

    for i, batch in enumerate(pmid_batches):
        comma_separated_pmids = ",".join(batch)

        request_params_efetch = {
            "db": "pubmed",
            "id": comma_separated_pmids,
            "retmode": "xml",
            "email": MAILTO,
        }

        print(f"Efetch request for {disease_name} with batch of {len(batch)} PMIDs.")
        try:
            response = get_with_retry(
                PUBMED_EFETCH_URL,
                request_params_efetch,
                context_label=f"{disease_name} (Efetch batch of {len(batch)} PMIDs.",
            )
            if response is None:
                print(f"Could not fetch batch for {disease_name}, skipping this batch")
                extract_succeeded = False
                continue
            XML_TREE = ET.fromstring(response.content.decode("utf-8"))
        except (requests.exceptions.RequestException, ET.ParseError) as e:
            print(
                f"Error fetching/parsing XML records for {disease_name} (batch {i + 1}): {e}"
            )
            extract_succeeded = False
            continue

        if response.status_code != 200:
            print(
                f"Error fetching XML records for {disease_name} ( {comma_separated_pmids}: {response.status_code} - {response.text}"
            )
            extract_succeeded = False
            continue

        PubmedArticleSet_ELEMENT = XML_TREE.find(".")
        if PubmedArticleSet_ELEMENT is not None:
            for PubmedArticle_ELEMENT in PubmedArticleSet_ELEMENT.findall(
                "PubmedArticle"
            ):
                raw_pubmed_records.append(PubmedArticle_ELEMENT)
        time.sleep(0.1)

    print(f"Fetched {len(raw_pubmed_records)} XML records for {disease_name}")
    return raw_pubmed_records, extract_succeeded


# Stage 2: transform(raw_records, disease_name)
# Convert raw Pubmed XML records into Sankofa entity dicts
def transform(raw_records, disease_name):
    entities = []
    relationships = []
    sources = []
    added_regions = set()

    for paper_xml_record in raw_records:
        current_pmid = "Unknown"  # Default for logging if PMID extraction fails
        try:
            # Per-paper error handling to skip malformed records
            # Extract PMID early for logging
            PMID_ELEMENT = paper_xml_record.find(".//PMID")
            if PMID_ELEMENT is not None and PMID_ELEMENT.text is not None:
                current_pmid = PMID_ELEMENT.text

            # MANDATORY DISEASE CLASSIFICATION GATE
            matched_disease_name_in_paper = parse_pubmed_disease_terms(
                paper_xml_record, disease_name
            )
            if matched_disease_name_in_paper == "Unknown":
                print(
                    f"Warning: Skipping paper (PMID: {current_pmid}) because disease'{disease_name}' was not confirmed in MesH, Keywords, Title, or Abstract"
                )
                continue

            # Extract other core fields from XML
            ArticleTitle_ELEMENT = paper_xml_record.find(".//ArticleTitle")
            ArticleTitle_TEXT = (
                ArticleTitle_ELEMENT.text
                if ArticleTitle_ELEMENT is not None
                and ArticleTitle_ELEMENT.text is not None
                else "No Title Available"
            )

            concatenated_abstract = []
            Abstract_ELEMENT = paper_xml_record.find(".//Abstract")
            if Abstract_ELEMENT is not None:
                AbstractText_ELEMENTS = Abstract_ELEMENT.findall("AbstractText")
                for AbstractText_ELEMENT in AbstractText_ELEMENTS:
                    if AbstractText_ELEMENT.text is not None:
                        concatenated_abstract.append(AbstractText_ELEMENT.text)
            concatenated_abstract_string = " ".join(concatenated_abstract)
            PublicationType_LIST_ELEMENTS = paper_xml_record.findall(
                ".//PublicationType"
            )
            Author_LIST_ELEMENTS = paper_xml_record.findall(".//Author")
            # Extract first author name for source contribution
            first_author = ""
            if Author_LIST_ELEMENTS:
                first_author_elem = Author_LIST_ELEMENTS[0]
                last_name = first_author_elem.findtext("LastName", "")
                fore_name = first_author_elem.findtext("ForeName", "")
                first_author = f"{last_name} {fore_name}".strip()

            doi_url = None
            ArticleIdList_ELEMENT = paper_xml_record.find(".//ArticleIdList")
            if ArticleIdList_ELEMENT is not None:
                for ArticleId_ELEMENT in ArticleIdList_ELEMENT.findall("ArticleId"):
                    if (
                        ArticleId_ELEMENT.attrib.get("IdType") == "doi"
                        and ArticleId_ELEMENT.text is not None
                    ):
                        doi_url = "https://doi.org/" + ArticleId_ELEMENT.text
                        break

            paper_source_url = (
                doi_url
                if doi_url is not None
                else "https://pubmed.ncbi.nlm.nih.gov/" + current_pmid + "/"
            )
            # Derive all fields we need
            # Entity_type for the database entity is based on abstract keyword scan
            disease_entity_type = determine_entity_type(
                concatenated_abstract_string
            )  # Reuse openalex.py helper logic

            confidence_tier_for_this_paper = determine_pubmed_confidence(
                PublicationType_LIST_ELEMENTS
            )

            region_name = extract_pubmed_region(Author_LIST_ELEMENTS)

            # Build disease entity
            disease_entity_dict = {
                "name": disease_name,
                "domain": "healthcare",
                "entity_type": disease_entity_type,
                "region": region_name,
                "expression": ArticleTitle_TEXT,
                "confidence": confidence_tier_for_this_paper,
                "contributor": "PubMed",
            }
            entities.append(disease_entity_dict)

            # Build entity_source record for the disease entity
            disease_entity_source_record = {
                "entity_name": disease_name,
                "domain": "healthcare",
                "source_name": "PubMed",
                "source_url": paper_source_url,
                "confidence": confidence_tier_for_this_paper,
                "context": ArticleTitle_TEXT,
                "source_author": first_author,
                "source_title": ArticleTitle_TEXT,
            }
            sources.append(disease_entity_source_record)

            # Build region entity (if not already added)
            if region_name not in added_regions:
                region_entity_type = (
                    "Continent" if region_name == "AFRICA" else "Country"
                )
                region_entity_dict = {
                    "name": region_name,
                    "domain": "geography",
                    "entity_type": region_entity_type,
                    "region": region_name,  # Self-referential for region entity
                    "expression": region_name,
                    "confidence": 3,  # Assumed high confidence for known region/countries
                    "contributor": "PubMed",
                }
                entities.append(region_entity_dict)
                added_regions.add(region_name)

            # Build entity_source record for the region entity
            region_entity_source_record = {
                "entity_name": region_name,
                "domain": "geography",
                "source_name": "PubMed",
                "source_url": paper_source_url,
                "confidence": confidence_tier_for_this_paper,
                "context": ArticleTitle_TEXT,
                "source_author": first_author,
                "source_title": ArticleTitle_TEXT,
            }
            sources.append(region_entity_source_record)

            # Build prevalent_in relationship
            prevalent_relationship_dict = {
                "from_entity_name": disease_name,
                "from_entity_domain": "healthcare",
                "to_entity_name": region_name,
                "to_entity_domain": "geography",
                "relationship": "prevalent_in",
                "confidence": confidence_tier_for_this_paper,
                "context": ArticleTitle_TEXT,
                "source_url": paper_source_url,
                "source_name": "PubMed",
                "source_author": first_author,
                "source_title": ArticleTitle_TEXT
            }
            relationships.append(prevalent_relationship_dict)

            # Check if paper mentions treatment (using TREATMENT_VOCABULARY only)
            concatenated_abstract_string_lower = concatenated_abstract_string.lower()
            treatment_for_disease = TREATMENT_VOCABULARY.get(
                disease_name, []
            )  # Get specific treatments for this disease, default to empty list

            for treatment_term in treatment_for_disease:
                treatment_term_lower = treatment_term.lower()
                if treatment_term_lower in concatenated_abstract_string_lower:
                    # Find specific treatment from vocabulary
                    found_treatment_name = treatment_term

                    treatment_entity_dict = {
                        "name": found_treatment_name,
                        "domain": "healthcare",
                        "entity_type": "Clinical",
                        "region": region_name,
                        "expression": ArticleTitle_TEXT,
                        "confidence": confidence_tier_for_this_paper,
                        "contributor": "PubMed",
                    }
                    entities.append(treatment_entity_dict)

                    # Build entity_source record for the treatment entity
                    treatment_entity_source_record = {
                        "entity_name": found_treatment_name,
                        "domain": "healthcare",
                        "source_name": "PubMed",
                        "source_url": paper_source_url,
                        "confidence": confidence_tier_for_this_paper,
                        "context": ArticleTitle_TEXT,
                        "source_author": first_author,
                        "source_title": ArticleTitle_TEXT
                    }
                    sources.append(treatment_entity_source_record)

                    treats_relationship_dict = {
                        "from_entity_name": found_treatment_name,
                        "from_entity_domain": "healthcare",
                        "to_entity_name": disease_name,
                        "to_entity_domain": "healthcare",
                        "relationship": "treats",
                        "confidence": confidence_tier_for_this_paper,
                        "context": ArticleTitle_TEXT,
                        "source_url": paper_source_url,
                        "source_name": "PubMed",
                        "source_author": first_author,
                        "source_title": ArticleTitle_TEXT
                    }
                    relationships.append(treats_relationship_dict)
        except Exception as error:
            print(
                f"Warning: Skipping malformed PubMed record (PMID: {current_pmid} for {disease_name} during transform: {error}"
            )
            continue
    return entities, relationships, sources


# Stage 3: load(entities, relationships, sources, db_session)
# Upsert everything into PostgreSQL with evidence-weighing and idempotency
def load(entities, relationships, sources, db_session):

    entity_name_to_id = {}
    relationship_type_name_to_id = {}

    try:
        # Step 1: Pre-load all relationship types
        relationship_types_rows = db_session.query(RelationshipTypes).all()
        for row in relationship_types_rows:
            relationship_type_name_to_id[row.name] = row.id

        # Ensure "prevalent_in" and "treats" relationship types exist
        for rel_name in ["prevalent_in", "treats"]:
            if rel_name not in relationship_type_name_to_id:
                new_rel_type = RelationshipTypes(name=rel_name)
                db_session.add(new_rel_type)
                db_session.flush()
                relationship_type_name_to_id[rel_name] = new_rel_type.id
                print(f"Added new relationship type: {rel_name}")
        db_session.commit()

        # Step 2: Upsert Entities and get their IDs
        for entity_dict in entities:
            entity_name = entity_dict["name"]
            domain = entity_dict["domain"]
            normalized_incoming = entity_name.lower().strip()

            existing_entity = (
                db_session.query(Entity)
                .filter(func.lower(func.trim(Entity.name)) == normalized_incoming)
                .filter_by(domain=domain)
                .first()
            )

            if existing_entity is not None:
                # Update confidence if strictly higher
                if entity_dict["confidence"] > existing_entity.confidence:
                    existing_entity.confidence = entity_dict["confidence"]
                entity_name_to_id[(entity_name, domain)] = existing_entity.id
                db_session.add(existing_entity)
            else:
                new_entity = Entity(**entity_dict, evidence_count=1)
                db_session.add(new_entity)
                db_session.flush()
                entity_name_to_id[(entity_name, domain)] = new_entity.id
                print(f"Added new entity: {entity_name}")

        # Step 3: Process Sources (EntitySources and RelationshipSources)
        for source_entry_dict in sources:
            source_name = source_entry_dict["source_name"]
            source_url = source_entry_dict["source_url"]
            # confidence_from_paper = source_entry_dict["confidence"]
            # context_from_paper = source_entry_dict.get("context", None)
            # Determine if this is an EntitySource or RelationshipSource entry
            if "entity_name" in source_entry_dict:  # This is an EntitySource entry
                entity_name = source_entry_dict["entity_name"]
                domain = source_entry_dict["domain"]
                entity_id = entity_name_to_id.get((entity_name, domain))

                if entity_id is None:
                    print(
                        f"Warning: Could not find ID for entity '{entity_name}' ({domain}) for source link '{source_url}' skipping entity source"
                    )
                    continue

                existing_entity_source = (
                    db_session.query(EntitySource)
                    .filter_by(entity_id=entity_id, source_url=source_url)
                    .first()
                )

                if existing_entity_source is None:
                    # Create the new EntitySource record
                    new_entity_source = EntitySource(
                        entity_id=entity_id,
                        source_name=source_name,
                        source_url=source_url,
                        source_author=source_entry_dict.get("source_author"),
                        source_title=source_entry_dict.get("source_title")
                    )
                    db_session.add(new_entity_source)

                    # Find the entity in th DB to update its evidence_count
                    entity_to_update = (
                        db_session.query(Entity).filter_by(id=entity_id).first()
                    )
                    if entity_to_update is not None:
                        entity_to_update.evidence_count += 1
                        db_session.add(entity_to_update)
                    else:
                        print(
                            f"CRITICAL ERROR: Entity with ID {entity_id} not found immediately after upserting. Skipping evidence_count update for source {source_url}."
                        )
                        continue

        # Step 4: Upsert Relationships and create their sources
        for relationship_dict in relationships:
            from_entity_name = relationship_dict["from_entity_name"]
            from_entity_domain = relationship_dict["from_entity_domain"]
            to_entity_name = relationship_dict["to_entity_name"]
            to_entity_domain = relationship_dict["to_entity_domain"]
            relationship_type_name = relationship_dict["relationship"]
            relationship_confidence_from_paper = relationship_dict["confidence"]
            relationship_context_from_paper = relationship_dict["context"]
            relationship_source_url = relationship_dict["source_url"]
            relationship_source_name = relationship_dict["source_name"]

            from_id = entity_name_to_id.get((from_entity_name, from_entity_domain))
            to_id = entity_name_to_id.get((to_entity_name, to_entity_domain))
            relationship_type_id = relationship_type_name_to_id.get(
                relationship_type_name
            )

            if from_id is None or to_id is None or relationship_type_id is None:
                print(
                    f"Warning: Skipping relationship due to unresolved entity/type IDs: {from_entity_name} -> {to_entity_name} ({relationship_type_name}) for source {relationship_source_url}"
                )
                continue

            existing_relationship = (
                db_session.query(EntityRelations)
                .filter_by(
                    from_entity_id=from_id,
                    to_entity_id=to_id,
                    relationship_id=relationship_type_id,
                )
                .first()
            )

            if existing_relationship is not None:
                # Relationship exists, check if this source has already been added to relationship_source
                existing_relationship_source_entry = (
                    db_session.query(RelationshipSource)
                    .filter_by(
                        relationship_id=existing_relationship.id,
                        source_url=relationship_source_url,
                    )
                    .first()
                )

                if existing_relationship_source_entry is None:
                    # Create the new RelationSource record
                    new_relationship_source_entry = RelationshipSource(
                        relationship_id=existing_relationship.id,
                        source_name=relationship_source_name,
                        source_url=relationship_source_url,
                        confidence=relationship_confidence_from_paper,
                        context=relationship_context_from_paper,
                        source_author=relationship_dict.get("source_author"),
                        source_title=relationship_dict.get("source_title"),
                    )
                    db_session.add(new_relationship_source_entry)

                    # Find the relationship in the DB to update its evidence_count and confidence
                    relationship_to_update = (
                        db_session.query(EntityRelations)
                        .filter_by(id=existing_relationship.id)
                        .first()
                    )
                    if relationship_to_update is not None:
                        relationship_to_update.evidence_count += 1
                        if (
                            relationship_confidence_from_paper
                            > relationship_to_update.confidence
                        ):
                            relationship_to_update.confidence = (
                                relationship_confidence_from_paper
                            )
                        db_session.add(relationship_to_update)
                    else:
                        print(
                            f"CRITICAL ERROR: Relationship with ID {existing_relationship.id} not found immediately after upserting. Skipping evidence_count/confidence update for source {relationship_source_url}."
                        )
                        continue
                else:
                    pass

            else:  # Relationship does not exist, create it fresh
                new_relationship = EntityRelations(
                        from_entity_id=from_id,
                        to_entity_id=to_id,
                        relationship_id=relationship_type_id,
                        confidence=relationship_confidence_from_paper,
                        context=relationship_context_from_paper,
                        evidence_count=1,
                )
                db_session.add(new_relationship)
                db_session.flush()

                # Create the first RelationshipSource record for this new relationship
                new_relationship_source_entry = RelationshipSource(
                        relationship_id=new_relationship.id,
                        source_name=relationship_source_name,
                        source_url=relationship_source_url,
                        confidence=relationship_confidence_from_paper,
                        context=relationship_context_from_paper,
                        source_author=relationship_dict.get("source_author"),
                        source_title=relationship_dict.get("source_title"),
                    )
                db_session.add(new_relationship_source_entry)
        db_session.commit()
        print("Load complete")

    except Exception as e:
        print(f"Load failed: {e}")
        db_session.rollback()
    finally:
        db_session.close()


def run_pubmed_ingestion(disease_name):
    print(f"Starting PubMed ingestion for: {disease_name}")

    raw_records, extract_succeeded = extract(disease_name)

    if not raw_records:
        if extract_succeeded:
            print(f"No records found for {disease_name}--- extraction completed successfully, no data exists.")
        else:
            print(f"No records found for {disease_name}--- extraction FAILED, this is NOT a verified absence, do not treat as checked")
        return extract_succeeded
    entities, relationships, sources = transform(raw_records, disease_name)
    db_session = SessionLocal()

    try:
        load(entities, relationships, sources, db_session)
    except Exception as e:
        print(f"Error during load stage for {disease_name}: {e}")
    finally:
        db_session.close()
    print(f"Ingestion complete for: {disease_name}")
    return extract_succeeded
