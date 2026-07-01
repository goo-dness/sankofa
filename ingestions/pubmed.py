import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from sqlalchemy.orm import Session

from ingestions.openalex import DISEASE_VOCABULARY, TREATMENT_VOCABULARY
from models.entities import Entity
from models.entity_relationships import EntityRelations
from models.entity_sources import EntitySource
from models.relations_type import RelationshipTypes
from models.relationship_sources import RelationshipSource

PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
RETMAX = 50
PUBMED_CAP = 500
EFETCH_BATCH_SIZE = 500
MAILTO = "goodnessakuba1708@gmail.com"

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
    paper_xml_records: ET.Element, target_disease_name: str
) -> str:
    target_disease_name_lower = target_disease_name.lower()

    # Check MeshHeadingList first
    mesh_head_list = paper_xml_records.find("MeshHeadingList")
    if mesh_head_list is not None:
        for mesh_heading in mesh_head_list.findall("MeshHeading"):
            descriptor_element = mesh_heading.find("DescriptorName")
            if descriptor_element is not None and descriptor_element.text is not None:
                descriptor_name_text = descriptor_element.text
                descriptor_name_text = descriptor_element.text.lower()
                if target_disease_name_lower in descriptor_name_text:
                    return target_disease_name

    # Check KeyWordList with Owner="NOTNLM" if not found in MesH
    keywordlist_elements = paper_xml_records.findall(
        ".//KeyWordList"
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
    articletitle_element = paper_xml_records.find(
        ".//AbstractTitle"
    )  # Search all AbstractTtitle
    articletitle_text = (
        articletitle_element.text.lower()
        if articletitle_element is not None and articletitle_element.text is not None
        else ""
    )
    concatenated_abstract = []

    abstract_element = paper_xml_records.find(
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
            or pub_type_text == "Meta-Aalysis"
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
                    affiliation_text_content = affiliation_text_element.text
                    affiliation_text_content = affiliation_text_content.lower()

                    # Critical: Scan against length-sorted country names (longest first)
                    for country_name in LENGTH_SORTED_AFRICAN_COUNTRY_NAMES:
                        country_name = country_name.lower()

                        if country_name in affiliation_text_content:
                            return country_name
    return "AFRICA"  # Fallback if no specific African country found


# STAGE 1: extract(disease_name)
# Fetch raw papers (PMID list then full XML) from pubmed for one disease
def extract(disease_name: str) -> List[ET.Element]:
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

    # Pagination loop for Esearch to get PMIDS
    while True:
        print(f"Esearch request for {disease_name} with retstart={offset}")
        request_params_esearch["retstart"] = offset
        try:
            response = requests.get(PUBMED_ESEARCH_URL, params=request_params_esearch)
            JSON_DATA = response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error making Esearch request for {disease_name}: {e}")
            break

        if response.status_code != 200:
            print(
                f"Error fetching PMIDs for {disease_name}: {response.status_code} - {response.text}"
            )
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
        return []
