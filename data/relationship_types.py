# data/relationship_types.py
# ------------------------------------------------------------
# Seed data for Sankofa relationship types.
# Each entry corresponds to a row in the `relationship_types` table.
# The ingestion pipelines (`seed_relationship_types` in seed.py) rely
# on this module being importable as `relationship_types_data`.
# ------------------------------------------------------------

relationship_types_data = [
    {
        "name": "treats",
        "label": "Treats",
        "domain": "pharmacology",
        "description": "A disease is treated by a drug or intervention.",
    },
    {
        "name": "derived_from",
        "label": "Derived From",
        "domain": "pharmacology",
        "description": "A molecule is derived from another parent molecule.",
    },
    {
        "name": "targets",
        "label": "Targets",
        "domain": "pharmacology",
        "description": "A drug targets a biological entity (protein, enzyme, etc.).",
    },
    {
        "name": "inhibits",
        "label": "Inhibits",
        "domain": "pharmacology",
        "description": "A drug inhibits the activity of a target.",
    },
    {
        "name": "binds_to",
        "label": "Binds To",
        "domain": "pharmacology",
        "description": "A drug binds to a target (affinity without functional effect).",
    },
    {
        "name": "expressed_by",
        "label": "Expressed By",
        "domain": "molecular",
        "description": "A protein or other biological entity is expressed by an organism.",
    },
]
