import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
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
def parse_pubmed_disease_terms(paper_xml_records, target_disease_name):
    target_disease_name = target_disease_name.lower()

    # Check MeshHeadingList first
    mesh_head_list = paper_xml_records.find("MeshHeadingList")
    if mesh_head_list:
        for mesh_heading in mesh_head_list:
            descriptor_element = mesh_heading.find("DescriptorName")
            if descriptor_element is None:
                descriptor_name_text = descriptor_element.text
                descriptor_name_text = descriptor_name_text.lower()
                if target_disease_name in descriptor_name_text:
                    return target_disease_name

    # Check KeyWordList with Owner="NOTNLM" if not found in MesH
    keywordlist_elements = paper_xml_records.findall(
        "KeyWordList"
    )  # search all KeyWordLists
    for keywordlist in keywordlist_elements:
        if (
            keywordlist.attrib.get("Owner") == "NOTNLM"
        ):  # check for exact attribute match
            for keyword in keywordlist.findall("Keyword"):
                if keyword.text is not None:
                    keyword_text = keyword.text
                    keyword_text = keyword_text.lower()
                    if target_disease_name in keyword_text:
                        return target_disease_name

    # Fallback to Title and Abstract if not found
    articletitle_element = paper_xml_records.find(
        "Abstract"
    )  # Search all AbstractTtitle
    articletitle_text = (
        articletitle_element.text if articletitle_element is None else ""
    )
    concatenated_abstract = []

    abstract_element = paper_xml_records.find(
        "Abstract"
    )  # Find the main Abstract element
    if abstract_element is not None:
        abstract_elements = abstract_element.findall(
            "AbstractText"
        )  # Find all AbstractText section
        for abstract_element in abstract_elements:
            if abstract_element.text is not None:
                concatenated_abstract.append(abstract_element.text)

    articletitle_text = articletitle_text.lower()
    concatenated_abstract = concatenated_abstract.lower()

    if target_disease_name in articletitle_text or concatenated_abstract:
        return target_disease_name  # Found in title or abstract
    else:
        return "Unknown"  # Target disease not explicitly found by classification rules


# HELPER FUNCTION: determine_pubmed_confidence(pub_type_list)
# Determine confidence tier based on publication type
def determine_pubmed_confidence(publication_type_list):
    for pub_type_element in publication_type_list:
        pub_type_text = pub_type_element.text
        if (
            pub_type_text == "Randomized Controlled Trial"
            or "Meta-Analysis"
            or "Systematic Review"
        ):
            return 3  # Established

    for pub_type_element in publication_type_list:
        pub_type_text = pub_type_element.text
        if (
            pub_type_text == "Review"
            or "CLinical Trial"
            or "Observational Study"
            or "Comparative Study"
        ):
            return 2  # Emerging

    return 1  # Traditionla, unclassified


# HELPER FUNCTION: extract_pubmed_region(author_list)
# Scans author affiliations for an African country name using SORTED_AFRICAN_COUNTRY_NAMES
def extract_pubmed_region(author_list):
    for author_element in author_list:
        affiliationinfo_list = author_element.findall("AffiliationInfo")
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
                    for country_name in AFRICAN_COUNTRY_NAMES:
                        country_name = country_name.lower()

                        if country_name in affiliation_text_content:
                            return country_name
    return "AFRICAN"  # Fallback if no specific African country found
