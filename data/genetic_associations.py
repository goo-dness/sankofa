# Hand-checked genetic associations that have a DIRECTION.
# Each row is one fact you have verified against a real paper.
# A row with an empty source_url is SKIPPED by the loader (step 3),
# so nothing unverified can enter the graph.

GENETIC_ASSOCIATIONS = [
    {
        "factor": "sickle cell trait",  # must match the existing entity name (lowercase)
        "disease": "malaria",  # the disease entity this fact is about
        "relationship": "protective_against",  # or "predisposes_to"
        "confidence": 1,  # 1-3; set it after you read the source
        "context": "Protects against severe malaria, not against infection.",  # the caveat
        "source_url": "",  # DOI or PubMed link. Empty = skipped
        "source_title": "",
        "source_author": "",
    },
    {
        "factor": "hemoglobin c",
        "disease": "malaria",
        "relationship": "protective_against",
        "confidence": 1,
        "context": "Strongest protection in people with two copies (CC).",
        "source_url": "",
        "source_title": "",
        "source_author": "",
    },
    {
        "factor": "duffy negative",
        "disease": "malaria",
        "relationship": "protective_against",
        "confidence": 1,
        "context": "Protects against Plasmodium vivax only, not falciparum.",
        "source_url": "",
        "source_title": "",
        "source_author": "",
    },
    {
        "factor": "ccr5 delta32",
        "disease": "hiv",
        "relationship": "protective_against",
        "confidence": 1,
        "context": "Two copies protect against infection with CCR5-using HIV strains.",
        "source_url": "",
        "source_title": "",
        "source_author": "",
    },
    {
        "factor": "apol1",
        "disease": "trypanosomiasis",
        "relationship": "protective_against",
        "confidence": 1,
        "context": "G1/G2 variants protect against Trypanosoma brucei rhodesiense (a separate pair from kidney risk).",
        "source_url": "",
        "source_title": "",
        "source_author": "",
    },
]
