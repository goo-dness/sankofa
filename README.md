# Sankofa Engine

> *Se wo were fi na wosankofa a yenkyi.*
> *"It is not wrong to go back for what you forgot."*

**Sankofa Engine** is a computational knowledge platform for Africa — a system that makes African knowledge queryable, computable, and connected. Think Wolfram Alpha, but built from African data, for African researchers.

---

## The Problem

Africa generates knowledge — in its research institutions, its communities, its oral traditions, its hospitals and laboratories. But that knowledge is scattered, siloed, and largely inaccessible to the researchers who need it most. A PhD student in Enugu should not have to cross five databases across three continents to answer one question about disease burden in her region.

Sankofa exists to change that.

---

## What Sankofa Does

Sankofa is not a search engine. It is a **knowledge graph** — a structured, computable network of African entities, relationships, and data points that a researcher can query with precision.

A researcher can ask:

> *"What pathogens cause the highest child mortality in West Africa, and what traditional compounds have been studied against them?"*

Sankofa traverses the graph — from epidemiological data to biological entities to ethnomedicinal records — and returns a connected answer, with confidence scores showing the strength of each relationship.

---

## Architecture

Sankofa is built in four layers:

```
┌─────────────────────────────────────┐
│  SL5  Natural Language (Litsi AI)   │
├─────────────────────────────────────┤
│  SL4  Query Engine                  │
├─────────────────────────────────────┤
│  SL3  Symbolic Expression Engine    │
├─────────────────────────────────────┤
│  SL2  African Knowledge Corpus      │
├─────────────────────────────────────┤
│  SL1  Atax LLM Runtime (2028+)      │
└─────────────────────────────────────┘
```

The current build targets **SL2 and SL4** — the corpus and the query engine. The natural language layer (Litsi) follows.

---

## Knowledge Schema

All knowledge in Sankofa is stored as **entities** and **relationships.**

### Entities

Every piece of knowledge — a disease, a pathogen, a protein, a statistic, a plant compound — is an entity with:

| Field | Description |
|---|---|
| `name` | Canonical name |
| `domain` | epidemiology, microbiology, ethnomedicine, clinical... |
| `entity_type` | disease, pathogen, compound, statistic, protein... |
| `region` | Geographic scope |
| `original_lang` | Language of origin for indigenous knowledge |
| `expression` | Computable form (sequence, formula, value) |
| `confidence` | 1 (Traditional), 2 (Emerging), 3 (Established) |

### Relationships

Entities connect to each other through typed, scored relationships:

| Relationship | Example |
|---|---|
| `causes` | Lassa virus → causes → Lassa fever |
| `treats` | Artemisinin → clinically treats → Malaria |
| `traditionally_treats` | Neem → traditionally treats → Malaria |
| `prevalent_in` | Malaria → prevalent in → West Africa |
| `encodes` | Gene X → encodes → surface protein |
| `studied_by` | AJOL paper → studies → Lassa fever |
| `corresponds_to` | Traditional remedy → corresponds to → Clinical compound |

### Confidence Tiers

Every entity and relationship carries a confidence score:

| Tier | Label | Meaning |
|---|---|---|
| 3 | Established | Peer-reviewed, replicated, WHO / EMBL sourced |
| 2 | Emerging | Single study, preliminary findings |
| 1 | Traditional | Ethnomedicine, oral record, community knowledge |

Tier 1 is not inferior — it is a **research lead.** Gaps between Traditional and Established evidence are original research opportunities.

---

## Data Sources

| Source | Layer | Type |
|---|---|---|
| WHO Global Health Observatory | Epidemiological | REST API |
| AJOL (African Journals Online) | Research | Scraping |
| AlphaFold | Molecular / Protein | REST API |
| EMBL | Genetic / Sequence | REST API |

---

## Tech Stack

| Component | Technology |
|---|---|
| API Framework | FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Validation | Pydantic |
| HTTP Client | httpx |
| Server | Uvicorn |
| Language | Python 3.12+ |

---

## Project Structure

```
sankofa/
├── app/               # FastAPI app entry point
│   ├── database.py           # DB connection and session
│   ├── config.py             # Environment config
│   │           # Core knowledge engine
├── models/           # SQLAlchemy models
│   ├── __init__.py
│   ├── entities.py
│   ├── entity_names.py
│   ├── entity_relationships.py
│   ├── entity_sources.py
│   └── entity_peoples.py
├── schemas/          # Pydantic schemas
│   ├── __init__.py
│   └── entities.py
└── router         # API endpoints
│   |--- entities.py
|   |--- entity_names.py
|   |--- entity_people.py
|   |--- entity_relationships.py
|   |--- entity_sources.py
|   |--- relations_type.py
├── ingestion/            # Data pipeline scripts
│   ├── who.py            # WHO GHO ingestion
│   ├── ajol.py           # AJOL scraper
│   ├── alphafold.py      # AlphaFold ingestion
│   └── embl.py           # EMBL ingestion
│   
│   
│
├── migrations/               # Alembic migrations
├── tests/
├── requirements.txt
|--- main.py
├── .env.example
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- PostgreSQL

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/sankofa.git
cd sankofa

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create PostgreSQL database
psql -U postgres -c "CREATE DATABASE sankofa_db;"

# Set up environment variables
cp .env.example .env
# Edit .env with your database credentials

# Run migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload
```

---

## Roadmap

### 2026

| Phase | Description | Status |
|---|---|---|
| Phase 1 | Knowledge Engine — entities, relationships, corpus | 🔨 In Progress |
| Phase 2 | WHO data ingestion pipeline | 🔨 In Progress |
| Phase 3 | AJOL, AlphaFold, EMBL pipelines | Planned |
| Phase 4 | Query Engine (SL4) | Planned |
| Phase 5 | Community + Learning Center | Planned |
| Phase 6 | Litsi — Natural Language Layer | Planned |

---

## The Ùmà Layer

*Ùmà* is the Igala word for knowledge.

The Ùmà layer is Sankofa's long-term ambition: a formal system that makes African indigenous knowledge **computable as reasoning** — not just stored as text. Traditional medicine, astronomical knowledge, mathematical systems, oral logic — represented in a form a machine can traverse and a researcher can query.

This is Phase 6/7. It is what makes Sankofa different from every other knowledge platform.

---

## Contributing

Sankofa is building a corpus that requires human expertise, not just automation. If you are a researcher, domain expert, or indigenous knowledge holder, your contribution matters.

Contribution guidelines coming soon.

---

## License

MIT License. See `LICENSE` for details.

---

*Built in Nigeria. For Africa. For the world.*
