# Sankofa Engine — Project Context

**Developer:** Goodness Akuba, Lagos, Nigeria. Self-taught software developer, aspiring AI systems programmer.
**Repo:** github.com/goo-dness
**Last updated:** July 2026

---

## 1. What Sankofa Is

Sankofa is a computational knowledge platform for Africa. The reference point is Wolfram Alpha, but African-centred: **symbolic reasoning over a knowledge graph — not RAG, not CRUD.**

The core complaint Sankofa exists to answer: general-purpose tools like Wolfram Alpha, when pushed into a specific domain like African health research, degrade into returning lists of papers instead of computed answers. A real user — a microbiology/biostatistics PhD student at Covenant University, Sankofa's first target user — described exactly this: she asked Wolfram a health question and got back sources to dig through herself, the same failure mode as a RAG chatbot. Sankofa's job is to have already done that digging, weighed the evidence, and return a synthesized, sourced, confidence-rated answer.

**North star:** *Sankofa should reason like a human does.* Not just retrieve facts, but chain them together, weigh evidence instead of collecting it uncritically, and know the difference between "this is false," "this is unknown," and "this hasn't been looked at yet."

**First domain:** Healthcare.

### Sankofa Engine — Layers

| Layer | Name | Status | What it does |
|-------|------|--------|-------------|
| 1 | Knowledge Foundation | ✅ Complete | Data ingestion and database. WHO, OpenAlex, PubMed, ChEMBL pipelines. Entities and relationships, confidence tiers, evidence weighing. |
| 2 | Computational Symbolic Engine | 🔄 In progress | Reasoning over the knowledge graph using recursive CTEs. weighing.py — weighs confidence and evidence counts. |
| 3 | AI Layer (Litsi) | ⏳ Next | Interprets and explains what the engine computes. RAG pipeline connecting Claude API to PostgreSQL. Architecturally distinct from the symbolic core — embeddings belong to Litsi, not to Sankofa's computation engine. |
| 4 | Ùmà Layer | 🔮 Final | Formalizes indigenous knowledge as computable reasoning. May use a logic-programming layer (pyDatalog or kanren) on top of the CTE foundation. |

### Long-Term Domain Scope

Healthcare is the first domain — not the only one. Sankofa's long-term ambition is breadth comparable to Wolfram Alpha's. Confirmed directly against Wolfram Language's own Documentation Center category list (screenshotted June 2026) as a reference point for the scale of "computational knowledge engine":

Core Language & Structure, Data Manipulation & Analysis, Visualization & Graphics, Machine Learning & LLMs, Symbolic & Numeric Computation, Higher Mathematical Computation, Strings & Text, Graphs & Networks, Images, Geometry, Sound & Video, Knowledge Representation & Natural Language, Time-Related Computation, Geographic Data & Computation, Scientific and Medical Data & Computation, Engineering Data & Computation, Financial Data & Computation, Social, Cultural & Linguistic Data.

Domains explicitly named for Sankofa's own expansion, beyond healthcare: general medicine, mathematics, biology, chemistry, economics, astronomy, space science — with more still to be scoped as the project matures.

This is a long-term expansion target, not a near-term build item. Healthcare remains the proving ground — the ingestion pattern, the evidence-weighing system (§5), the relationship-type vocabulary approach, and the eventual Computational Symbolic Engine (Layer 2) are all being built here first specifically so they generalize cleanly to these other domains later, rather than being healthcare-specific one-offs.

---

## 2. Project Structure (flat, verified against live filesystem, 2026-08-10)

Real root is `sankofa/`, flat at repo root — no `backend/` subfolder. A `backend/` nesting briefly existed and was removed on 2026-08-10 after it started causing import errors (anything resolving `from app.database import ...` etc. needs `app/`, `models/`, `ingestions/` etc. as direct siblings of the invocation root, not nested a level deeper). `scripts/` also sits at repo root, alongside everything else, not inside any subfolder.

```
sankofa/                    (repo root)
├── README.md
├── main.py
├── alembic.ini
├── requirements.txt
├── CONTEXT.md
├── SL4_ARCHITECTURE.md
├── .env / .env.example
├── app/
│   ├── database.py
│   ├── config.py
│   └── http_utils.py     (shared get_with_retry — used by every ingestion)
├── models/
│   ├── entities.py
│   ├── entity_names.py
│   ├── entity_relationships.py    (EntityRelations — has derived_from/derivation_depth, see §13 2026-08-01)
│   ├── entity_sources.py
│   ├── entity_people.py
│   ├── relationship_sources.py
│   ├── relations_type.py
│   └── coverage.py       (IngestionCoverage — relationship_type-granular, see §13 2026-08-01)
├── schemas/               (mirrors models 1:1, ConfigDict from_attributes=True — entities, entity_names, entity_people, entity_relationships, entity_sources, relations_type, relationship_sources)
├── routers/               (mirrors models 1:1, one router per table — entities, entity_names, entity_people, entity_relationships, entity_sources, relations_type, relationship_sources; no engine.py yet, planned for Layer 2 API per SL4_ARCHITECTURE.md §6)
├── computation/           (Computational Symbolic Engine — Layer 2)
│   ├── __init__.py
│   ├── queries.py         (CTE SQL queries)
│   ├── executor.py        (execute_single_hop, execute_two_hop, etc.)
│   ├── weighing.py        (aggregate_confidence, aggregate_evidence, weigh_chain, weigh_derived_fact)
│   ├── contradictions.py  (detect_contradictions, CONFLICT_PAIRS)
│   └── epistemic.py       (resolve_epistemic_state, EpistemicState enum)
│   (rules.py not yet created — Layer 2/3 derivation, blocked on expressed_by bridge, see §13 2026-08-09)
├── data/
│   ├── relationship_types.py
│   └── seed.py           (owns all orchestrator functions — run_who_ingestion(), run_openalex(), run_pubmed(), run_chembl(), record_coverage())
├── ingestions/
│   ├── who.py
│   ├── openalex.py       ✅ complete, includes causes detection + organism name normalization (§13 2026-08-01, 2026-08-09)
│   ├── pubmed.py         ✅ complete, includes causes detection + organism name normalization (§13 2026-08-01, 2026-08-09)
│   └── chembl.py         ✅ complete, `expressed_by` widening not yet started (§13 2026-08-09)
├── scripts/
│   ├── cleanup_duplicates.py           (one-time — literal duplicate entities from before the unique name+domain index existed)
│   ├── normalize_causal.py             (one-time — renames/merges informal CausalAgent organism names to formal binomial names, per ORGANISM_NAME_MAP)
│   └── dedupe_entity_relations.py      (one-time — merges duplicate entity_relations rows left over from historic entity merges, recomputes evidence_count/confidence from relationship_sources)
├── migrations/            (Alembic — env.py, script.py.mako, versions/)
└── tests/                 (empty — no tests written yet)
```

---

## 3. Database Schema

**entities**
`id, name, domain, entity_type, region, original_lang, expression, confidence (int 1-3), evidence_count (int, default 1), contributor, timestamps`

**entity_relationships**
`id, from_entity_id, to_entity_id, relationship_id (FK → relationship_types), confidence (int 1-3), evidence_count (int, default 1), context, timestamps`

**entity_sources**
`id, entity_id, source_name, source_url, timestamps` — provenance trail for entities.

**relationship_sources** *(new — added mid-project, see §5)*
`id, relationship_id, source_name, source_url, confidence (this specific source's own rating), context, timestamps` — provenance trail for relationships, mirrors entity_sources.

**relationship_types**
Lives in the DB, not an enum. 50+ seeded relationships across domains: pathology, epidemiology, pharmacology, molecular, ethnomedicine, clinical, genetics, institutional, general. Includes `causes`, `treats`, `traditionally_treats`, `prevalent_in`, `studied_by`, `protective_against`, `structurally_similar_to`, and more — see `data/relationship_types.py` for the full list.

**Other tables (not yet populated by any ingestion):** `entity_names`, `entity_people`.


**ingestion_coverage**
`id, domain, disease_name, source_name, relationship_type, last_ingested_at` — tracks which (disease, source, relationship_type) combinations have been ingested. Enables three-state epistemic awareness (§9) at relationship-type granularity. Unique constraint `uq_disease_source_reltype` on `(disease_name, source_name, relationship_type)`. Populated by each ingestion pipeline via `record_coverage()` in `data/seed.py`, once per relationship type actually touched in a run.

**Confidence tiers:** 1 = Traditional, 2 = Emerging, 3 = Established.

**Entity types in use:** Epidemiological, Clinical, Indigenous, Biological, Institutional, Country, Continent, region.

---

## 4. Ingestion Pipelines

All ingestions follow the same three-stage pattern: **extract → transform → load.** Idempotent by design — safe to re-run.

### WHO GHO — ✅ Complete
- Source: `ghoapi.azureedge.net/api/`
- Countries: NGA, GHA, KEN, ETH, ZAF, UGA, TZA, CMR, SEN, CIV
- Indicators live: Malaria, HIV, Tuberculosis, Child Mortality, Maternal Mortality, Pneumonia
- Cholera dropped (no reliable WHO GHO code); deferred to text-source ingestion
- Produces: disease entities, statistic entities (one per country/year), region entities, `measures` and `prevalent_in` relationships

### OpenAlex — ✅ Complete
- Source: `api.openalex.org/works` — replaced AJOL (no functioning AJOL API exists)
- Requires a free API key (`api_key` param) — OpenAlex introduced usage-based pricing; unauthenticated requests get a small one-time credit only. Free key = $1/day budget, more than sufficient for this project's scale.
- Filter uses `title.search.exact` (not `title.search` — the plain `.search` variant caused persistent 504 timeouts when combined with continent/open-access/year filters; `.search.exact` is the cheaper substring-match path)
- 35-disease vocabulary across 5 tiers: major infectious diseases, NTDs, genetic conditions, maternal/child health, outbreak diseases
- Treatment detection: scans `TREATMENT_VOCABULARY[disease_name]` against abstract text only — no generic keyword placeholders like "[disease] treatment"
- Region extraction: African country ISO codes checked against author institution `country_code`, "AFRICA" fallback
- Cap: 500 papers per disease per run, cursor-paginated

### PubMed — ✅ Complete
- Source: NCBI E-utilities (ESearch → EFetch, two-step, XML not JSON)
- Query filter restricts to papers with a real African country name in an author's `[Affiliation]` field — confirmed necessary after a false positive was caught in testing (a Thailand-authored paper about peacekeepers in South Sudan matched a naive `AND Africa` search)
- `AFRICAN_COUNTRY_NAMES` must be **length-sorted, longest first**, before any substring scan — confirmed necessary because "Niger" is a substring of "Nigeria" and would otherwise mismatch real Nigerian-authored papers
- Disease classification: three-step fallback — MeSH headings → KeywordList (`Owner="NOTNLM"`) → title/abstract text scan. Recently indexed papers frequently lack MeSH entirely. Papers where the disease can't be confirmed by any of the three steps are explicitly skipped (mandatory gate), not defaulted through.
- Confidence: derived from `PublicationTypeList` tags (RCT/Meta-Analysis/Systematic Review = 3, Review/Clinical Trial/Observational = 2, else 1) — known to be an inconsistent signal since PubMed's own tagging under-classifies some papers
- Reuses `DISEASE_VOCABULARY` and `TREATMENT_VOCABULARY` from `openalex.py` (imported, not duplicated)
- Real bugs caught during implementation: a call site referencing a function by the wrong name (`parse_pubmed_disease_classification` vs. the actual `parse_pubmed_disease_terms`); wrong dictionary keys in `load()`'s relationship step (`"to_entity_dict"` instead of `"to_entity_name"`) that caused every relationship insert to fail silently while entities still saved — a reminder that partial success in early steps can mask a total failure in a later step
- `run_pubmed_ingestion()` and `run_pubmed()` (the per-disease and full-vocabulary orchestrators) live in `data/seed.py`, not in `pubmed.py` — same separation of concerns as `who.py`/`openalex.py`

### ChEMBL — ✅ Complete
- Source: `ebi.ac.uk/chembl/api/data/` — REST, JSON, paginated (`limit`/`offset`, max limit 1000, `page_meta` block gives `total_count` and `next`)
- Key endpoints confirmed: `/molecule` (compound data, `max_phase` field for approval status), `/mechanism` (drug → mechanism of action → target, e.g. `mechanism?molecule_chembl_id=CHEMBL998`), `/target` (searchable by name), `/activity` (bioactivity measurements, IC50/Ki values — 13M+ rows, must be filtered tightly, never pulled unfiltered)
- Purpose: populates currently-empty relationship types `targets`, `inhibits`, `binds_to`, `derived_from` — real pharmacological mechanism data, not just "drug X exists"


### Scope decision (locked)
No further new data sources after ChEMBL. Europe PMC was on the original roadmap but has been deliberately dropped — the priority now is finishing ChEMBL and moving straight into the Computational Symbolic Engine (Layer 2). Ethnomedicine-focused ingestion (§7) remains the identified strategic gap but is explicitly deferred past the engine, not before it — "build fast" means no more dataset detours until there's a working reasoning layer.

---

## 5. The Evidence-Weighing Redesign (major architectural fix)

**The problem, caught mid-project:** the original `load()` logic skipped any entity or relationship that already existed. This meant confidence got permanently frozen at whatever the *first* paper contributed — if paper #1 was a weak case report and papers #2–50 were strong RCTs all confirming the same fact, the relationship stayed at confidence 1 forever. This directly contradicted the north star: a human's confidence in a claim grows as independent evidence accumulates: this system's didn't.

**The fix:**
- Added `evidence_count` to `entities` and `entity_relationships`
- Added the new `relationship_sources` table (relationships previously had no provenance trail at all — only entities did)
- Changed `load()` from skip-on-duplicate to strengthen-on-new-evidence:
  - Check whether this exact `source_url` was already recorded
  - If yes → this is a re-run, do nothing (idempotency preserved)
  - If no → increment `evidence_count`, update `confidence` only if the new value is **strictly higher** (max, not average — one strong RCT should outweigh ten weak case reports, not get diluted by them)
- This logic is now standard across `who.py` and `openalex.py`; `pubmed.py` is being built to this standard from the start

**Migration note:** adding `NOT NULL` columns to tables with existing rows requires a `server_default` (e.g. `server_default='1'`) — Postgres will reject the migration otherwise, since existing rows have no value to backfill.

---

## 6. Architectural Patterns (established, apply to every new ingestion)

- **Region entities are built inside `transform()`, never inside `load()`.** `load()` is fully generic — it has no special-case knowledge of what an entity "means." An `added_regions` set (scoped per-run, inside `transform()`) prevents duplicate region entities within one ingestion pass.
- **`transform()` returns three separate lists:** `entities`, `relationships`, `sources`. `source_url` is never embedded inside an entity dict — it isn't a real column on the `entities` table, and unpacking it directly into the model constructor causes a runtime error.
- **Treatment entities are only created from `TREATMENT_VOCABULARY` matches.** No generic keyword-triggered placeholders (e.g. "malaria treatment") — this was tried early and explicitly rejected as low-value, uninformative graph data.
- **Per-paper try/except, not per-batch.** One malformed record must not discard an entire disease's worth of otherwise-good data — this exact bug once caused OpenAlex to silently skip diseases with no visible error.
- **`evidence_count`/constructor fields must be set inside the model constructor call**, not as a separate attribute assignment afterward — the latter causes Pyright type errors against SQLAlchemy's declarative Column typing.
- **Network requests go through `app/http_utils.py`'s `get_with_retry()`, never a bare `requests.get()`.** Added after repeated real connection drops (unstable rain-affected internet) killed entire ingestion runs on a single dropped packet. Retries up to 3 times with a short delay, returns `None` on total failure — every call site must check `if response is None:` immediately after, since `.json()` or `.content` on `None` crashes. Shared across `who.py`, `openalex.py`, and `pubmed.py` rather than reimplemented per file, same principle as importing `DISEASE_VOCABULARY` once instead of duplicating it.

---

## 7. The Ethnomedicine Gap — the strategic priority

Of the 50+ relationship types already seeded, six are ethnomedicine-specific and **currently have zero data feeding them**: `traditionally_treats`, `corresponds_to`, `documented_in`, `practiced_by`, `contains`, `prepared_as`.

This is deliberately identified as Sankofa's actual point of differentiation. WHO GHO exists. OpenAlex exists. Nobody has built a confidence-tiered, queryable, evidence-weighed graph of African traditional medicine at scale. This is the gap that makes Sankofa not-just-another-Wolfram-Alpha.

Also currently unpopulated: the genetic/protective layer (`protective_against`, `predisposes_to`, `resistant_to` — e.g. sickle cell trait's protective relationship to malaria, a flagship example of African-relevant multi-hop reasoning) and the vector/transmission layer (`transmitted_by`, `vector_of`, `spreads_via` — most NTDs in the vocabulary are vector-borne and this mechanism data doesn't exist yet).

**Planned order:** finish PubMed → Europe PMC → ChEMBL → then a dedicated ethnomedicine-targeted ingestion pass.

---

## 8. Business Model & Distribution

**The core pricing logic:** Sankofa does not sell facts — every underlying source (WHO GHO, OpenAlex, PubMed, eventually ChEMBL) is free and public. What Sankofa sells is the *time* a researcher would otherwise spend finding, cross-referencing, and weighing all of that themselves. Same model as Wolfram Alpha Pro: the math was never scarce, the computation and synthesis is what people pay for. Confidence tiers and `evidence_count` aren't just architecture — they're the visible receipt proving the synthesis work was actually done, which is the entire monetization argument made concrete.

**Three product surfaces, mapped to what's actually worth paying for:**
- **Query Interface** — likely stays free. Charging just to *ask* a question when the raw evidence is public contradicts Sankofa's own "accessible, African price points" positioning, and is what gets first users like the Covenant University researcher in the door.
- **Research Notebook + assistant** — the primary paid surface. Value is saved time and a structured working environment around computed answers, not exclusive access to facts.
- **Community / Learning Centre** — mentorship and researcher connection is the one truly scarce resource (people's time and attention, unlike facts, isn't abundant); freemium for learning content.

**Distribution — narrow before broad, deliberately:** with no finished query engine yet, broad launch would mean users hitting an unfinished product — hard to undo once that story spreads. Current plan is finding 4–5 more researchers like the validated Covenant University contact through warm introductions (her supervisor, her department, her research networks) rather than public launch channels. Explicitly rejecting hype-driven "check out my app" distribution culture (WhatsApp founder groups, launch-day noise) in favor of quiet, evidence-backed credibility — slower, but matches Sankofa's actual differentiator.

**Comparison worth remembering:** Claude Science (Anthropic, launched June 2026) pulls from the same public sources (PubMed, OpenAlex among its 60+ connected databases) but produces session-bound artifacts for one researcher's one project — no persistent, evidence-weighted fact that compounds in value the way a Sankofa entity does. Confirms the "time, not access" model is sound, but is a personal productivity tool, not a competing knowledge graph.

---

## 9. Computational Symbolic Engine (Layer 2) — Formal Design Requirement (not yet built)

**Requirement: Three-state epistemic awareness.**

A human expert distinguishes three states of knowledge; Sankofa's query engine must too:

1. **Known** — a relationship exists, backed by ≥1 source. Return it with confidence tier and evidence_count.
2. **Knowably absent** — the domain was ingested, nothing was found. Say so explicitly: "no established relationship found."
3. **Uncharted** — the domain hasn't been ingested yet. Say so explicitly, distinct from state 2 — this is a coverage gap, not a negative finding.

Without this distinction, an empty query result is ambiguous — a researcher can't tell if Sankofa looked and found nothing, or never looked at all. This makes the system unreliable for real research use.

**Implementation note:** `evidence_count = 0` cannot currently exist by design (relationships only get created when evidence exists), so absence-in-graph already correctly means "no evidence found during ingestion." The query engine needs to surface this classification explicitly at answer time, not just return empty.

**Coverage registry:** the `ingestion_coverage` table (§3) tracks which diseases have been ingested by which sources, enabling full three-state epistemic awareness. Each pipeline writes a row via `record_coverage()` in `data/seed.py`.

---

## 10. Roadmap

**Immediate (locked, no further additions):** ChEMBL ingestion → straight into the Computational Symbolic Engine (Layer 2). PubMed is done; Europe PMC has been deliberately dropped from the plan; ethnomedicine-targeted ingestion is deferred until after the engine exists, not before.

**Current status (July 2026):** paused on heavy implementation to close a foundational gap — working through Charles Petzold's *Code* to understand what Python and the underlying hardware are actually doing, rather than continuing to translate pseudocode into syntax without full comprehension. Still coding in small amounts (bug fixes, small additions) during this period, not fully stopped. This directly feeds the eventual C/CPython-internals work needed for OpenShark later — not a detour from the long-term arc, front-loaded foundation for it.

**After ChEMBL:** Computational Symbolic Engine (Layer 2) — recursive CTEs + plain Python. This is where the three-state epistemic awareness requirement (§9) gets implemented, and where confidence/evidence_count actually get *used* in synthesized answers rather than just stored. Code lives in `computation/` (internal codename; the engine itself is Layer 2, not a separate "SL4" product).

**After the engine:** frontend, then Litsi (Layer 3) — the AI layer (RAG pipeline connecting Claude API to PostgreSQL), kept architecturally distinct from the symbolic core. Embeddings belong to Litsi, not to the computation engine — this separation is deliberate and must be maintained.

**Long-term (5-company, 10-year arc):** Space Catalog (deployed) → Sankofa Engine (active) → Litsi → OpenShark/Atax LLM Runtime (C, hardware-agnostic AI inference runtime, 2027–2028+) → embedded/chip-level work.

---

## 11. Working Method (how this project gets built)

- **Pseudocode-first, real code only on request.** Claude writes the pseudocode directly in chat (Gemini/Zed no longer used for pseudocode generation, as of 2026-08-09 — see Decision Log) in a consistent pseudocode style (ALL CAPS actions, `//` comments, FUNCTION/END FUNCTION) before any real code is written, so the developer types every line by hand and understands it — no copy-pasting, ever.
- **The assistant provides architecture decisions, pseudocode, and file-level guidance only.** The developer types all real code by hand. Never output complete, runnable code. If the developer explicitly says "write the code" for a specific fix, that is the only exception — otherwise pseudocode only, always.
- **Verify against real API output before writing logic.** Every ingestion source's actual JSON/XML shape gets pulled and inspected via curl before pseudocode is finalized — several real bugs (missing `continent` field on OpenAlex institutions, PubMed's inconsistent MeSH tagging, the "Niger"/"Nigeria" substring bug) were only caught this way, not by reading documentation.
- **Explain code line by line.** Standing rule across all sessions.
- **One clean file swap over incremental patches** when multiple interconnected bugs need fixing at once — safer than tracking five small edits by memory, especially late in a session.

---

## 12. Brand Identity (locked)

**Colours:** Charcoal `#1A1A1A`, Ochre `#8B4513`, Copper `#B87333`, Gold `#C9A84C`, Ivory `#F5F0E8`, Ash `#6B6355`
**Typography:** Cormorant Garamond / Crimson Pro / Source Code Pro
**Tagline:** *"Se wo were fi na wosankofa a yenkyi."*

---

## 13. Decision Log

Running log of standalone decisions that don't belong inside a specific architecture section — kept dated so the reasoning behind a choice isn't lost later. Newest entries go on top.


### 2026-08-09 — `expressed_by` (protein→organism) bridge relationship confirmed and named; `treats + treats → treats` rule ruled out

**Decided:** The originally planned first Layer 2 inference rule
(`inhibits + causes → treats`, locked 2026-07-21) was tested against
live data via SQL and confirmed to produce zero composable entity
pairs — ChEMBL's protein/enzyme target entities and the `CausalAgent`
(pathogen/organism) entities from `causes` share no entity in common,
because no relationship currently bridges a protein target to the
organism that expresses it.

A substitute rule was considered and explicitly rejected:
`treats + treats → treats` (deriving a new `treats` fact by chaining
two existing `treats` facts via `derived_from`). This does not fill
the missing hop — it manufactures a "new" derived fact out of
relationships that already independently exist, which is exactly the
confidence-laundering pattern the `TIER_SCORE`/hard-tier-cap design
(2026-07-21) was built to prevent. Two independently-sourced `treats`
facts about a disease do not imply a third, novel `treats` fact.

**Fix (confirmed, not yet built):** add a real `expressed_by`
relationship (protein → organism) using organism data ChEMBL's
`/target` endpoint already returns — confirmed via the ChEMBL schema
docs (https://www.ebi.ac.uk/chembl/api/data/target/schema): `/target`
carries an `organism` field directly on the target record
(species-level, e.g. `"Plasmodium falciparum"`); `/target_component`
goes one level deeper with per-component `organism` + `tax_id`, for
the rarer multi-component (protein complex/family) case. Since
`chembl.py` already calls `/target` for mechanism data, this is a
widening of the existing target-fetch step, not a new data source —
stays inside the "no new sources after ChEMBL" lock (§4).

This produces a real 3-hop derived chain instead of the broken 2-hop
one:
```
molecule --inhibits--> protein --expressed_by--> organism --causes--> disease
```
Every premise is independently sourced and load-bearing; the existing
depth/decay math (`MAX_DEPTH`, `DECAY = 0.75`, min-of-premises
tiering) still applies unchanged.

**Relationship name — `expressed_by` chosen over `belongs_to`:**
`belongs_to` reads taxonomic/categorical (species membership);
`expressed_by` is the standard biological framing for "this
protein/gene product originates from this organism's genome," matches
how ChEMBL itself talks about targets, and reads correctly as a
mechanistic step in the chain above.

**Why:** Routing around a structural gap with a substitute inference
rule was rejected as confidence laundering — same principle as the
hard tier cap. The correct fix is adding the real missing data
connection, not inventing a rule that avoids needing it.

**Rules out:** `treats + treats → treats` (or any rule deriving
`treats` by chaining existing `treats` facts against themselves) as a
Layer 2 composition rule, permanently. `belongs_to` as the bridge
relationship name.

**Not yet done:**
- Seed `expressed_by` into `relationship_types`
- Widen `chembl.py` extract/transform/load to capture the `organism`
  field off the existing target fetch and write the new relationship
- Verify exact shape of the `organism` field via a real `curl` on a
  malaria/anemia-slice target ID (since `SINGLE PROTEIN`,
  `PROTEIN COMPLEX`, and `PROTEIN FAMILY` target types may return
  differently) before pseudocoding
- Re-scope `rules.py`'s first composition rule around the 3-hop chain
  above instead of the original 2-hop `inhibits + causes` pairing

**Unblocks:** ChEMBL extract/transform pseudocode can proceed once the
real `organism` field shape is confirmed via curl.

### 2026-08-01 — ChEMBL max_phase_for_ind key typo fixed (confidence tiering was silently broken)

**Decided:** Fixed a dict key typo in chembl.py's transform() dedupe
block — initialized as `max_phase_for_ind`, updated as `max_phase_for_id`
(one letter off). The KeyError on update was swallowed by the
surrounding per-record try/except, so it failed silently every time.
Net effect: `max_phase_for_ind` stayed frozen at 0.0 forever, so every
ChEMBL "treats" relationship fell through to confidence=1 (Traditional)
regardless of actual clinical trial phase.

**Why:** Caught via line-by-line review, not by symptom — same silent
failure mode as the earlier `indication_refs` field-name bug.

**Rules out:** N/A — typo fix, no design change.

**Unblocks:** ChEMBL confidence tiering now works as designed. Not yet
verified via live run — re-run ChEMBL for a disease with a known Phase 4
drug (malaria + an artemisinin combination) and confirm treats_confidence
lands on 3, not 1.

### 2026-08-01 — Coverage granularity (Option B) implemented: relationship_type added to ingestion_coverage

**Decided:** Closes the open item from 2026-07-29/30 — `ingestion_coverage`
now tracks coverage per `(disease_name, source_name, relationship_type)`,
not just per `(disease_name, source_name)`. `models/coverage.py`'s
`IngestionCoverage` gained a non-nullable `relationship_type` column; the
unique constraint was renamed `uq_disease_source_reltype` and now spans
all three fields. Table was truncated as part of the migration (same
precedent as the entity_sources/relationship_sources author/title
migration) — no backfill.

`record_coverage()` in seed.py gained a required `relationship_type`
parameter. Every orchestrator (`run_who_ingestion`, `run_openalex`,
`run_pubmed`, `run_chembl`) now calls it once per relationship type
actually touched in that run, derived from the real `relationships` list
each `transform()` produced — not from a static per-pipeline "capability
list." `run_openalex_ingestion()`, `run_pubmed_ingestion()`, and
`run_chembl_ingestion()` all changed their return signature from a single
`extract_succeeded` bool to `(extract_succeeded, touched_relationship_types)`
to carry this back to seed.py.

WHO is the one deliberate exception: `transform_to_entities()`
unconditionally emits both `measures` and `prevalent_in` for every row
(no vocabulary-match branching like OpenAlex/PubMed's `treats` detection),
so the zero-data-found branch in `run_who_ingestion()` hardcodes both
types rather than deriving from an empty relationships list — a true
statement about that pipeline's deterministic logic, not an assumption.

**Why:** A researcher asking "does X treat Y" needs coverage precision at
the relationship-type level, not just disease/source — the same
distinction the extraction_succeeded fix drew between "checked, found
nothing" and "never checked." Deriving touched types from real per-run
output avoids the same false-KNOWABLY_ABSENT trap.

**Rules out:** A static per-pipeline relationship-type capability list as
the source of truth for coverage rows.

**Known trade-off, accepted:** if extraction succeeds but a specific
relationship type produces zero rows this run (e.g. OpenAlex scans an
abstract but finds no TREATMENT_VOCABULARY match), no coverage row is
written for that type — it reads as UNCHARTED rather than
KNOWABLY_ABSENT, even though the check genuinely happened. Deliberate
cost of never fabricating a coverage claim from an assumed list.

**Status — NOT YET verified via live run.** Migration applied and
confirmed via `\d ingestion_coverage`. All four Python files edited via
find/replace, not yet run end-to-end. Next session should start with:
one pipeline run (OpenAlex, malaria), then:
`SELECT disease_name, source_name, relationship_type FROM ingestion_coverage WHERE source_name = 'OpenAlex' AND disease_name = 'malaria';`
— expect two rows (prevalent_in, treats), not one merged row.

**Unblocks:** Once verified, closes the last open item blocking real
three-state epistemic queries in Layer 2 (§9).

### 2026-07-29/30 — Ingestion coverage: extraction_succeeded signal threaded through all four pipelines + seed.py

**Decided:** Extended the existing but silently-broken coverage
tracking (seed.py's record_coverage()/IngestionCoverage — this
already existed, wasn't discovered until seed.py was reviewed
mid-session). Problem: seed.py was calling record_coverage()
unconditionally after every ingestion run, regardless of whether the
underlying API call actually succeeded — a transient API failure
would get permanently recorded as "checked, nothing found"
(KNOWABLY_ABSENT), indistinguishable from a genuine empty result.

Fix: each pipeline's extract() now returns a
(data, extraction_succeeded) tuple (chembl.py returns it as a
"success" dict key instead, since it already returns a dict). Every
existing silent failure branch (response is None, non-200 status,
JSON/XML decode errors, request exceptions) now sets
extraction_succeeded = False instead of just printing and continuing.
Each run_*_ingestion() orchestrator returns that boolean up to
seed.py, which now only calls record_coverage() when the run
genuinely succeeded — printing a distinguishing message either way so
failures are visible in logs, not just swallowed.

**Status — CONFIRMED via pasted-back file review:**
- seed.py — fixed and verified (including a real indentation bug
  introduced mid-fix, caught and corrected)

**Status — fix given, NOT YET verified via paste-back (do this first
in the next session):**
- pubmed.py — extract() and run_pubmed_ingestion()
- who.py — extract_who_data()
- openalex.py — extract_openalex_data() and run_openalex_ingestion()
  (this is IN ADDITION TO the abstract_inverted_index/region-evidence
  fixes from earlier, which ARE confirmed)
- chembl.py — extract() and run_chembl_ingestion() (IN ADDITION TO
  the mesh_id/max_phase/field-name/ref-url fixes from earlier, which
  ARE confirmed)

**Open, locked decision not yet implemented:** Coverage granularity
decided as Option B — per (disease, source, relationship_type), not
just per (disease, source). record_coverage()'s current signature
(db, domain, disease_name, source_name) has no relationship_type
parameter, and each pipeline's load() doesn't yet declare which
relationship types it's capable of producing on a given run. Needs
models/coverage.py (not yet seen) before this can be scoped further —
next session should start by requesting that file.

**Why:** A researcher asking Sankofa "does X treat Y" deserves to
know the difference between "we checked, no relationship exists" and
"we don't actually know, our last check failed" — silently
mislabeling the second as the first is worse than having no coverage
tracking, since it looks authoritative while being wrong.

### 2026-07-29 — ChEMBL and OpenAlex ingestion bugs fixed (mesh_id loop scope, null max_phase, wrong field names, region evidence gating)

**Decided:** Four bugs fixed across chembl.py and openalex.py, found via
line-by-line review checked against real API responses/docs, not assumed
field names.
- chembl.py: molecule/mechanism/target fetch block was indented inside
  the `for mesh_id in mesh_ids:` loop, causing redundant refetching for
  multi-mesh-id diseases (tuberculosis, dengue, leishmaniasis). Dedented
  to run once per disease.
- chembl.py: `float(max_phase_for_ind)` crashed on null and silently
  dropped the whole indication record. Now defaults to -1.0 (unknown
  tier), matching the existing confidence-tier comment's intent.
- chembl.py: code read `current_indication_refs`; real ChEMBL field
  (confirmed via curl) is `indication_refs`. Every "treats" relationship
  had been falling back to a generic molecule-page source instead of
  real ClinicalTrials/FDA refs. Fixed, plus a `ref_id`-based fallback
  URL for refs missing `ref_url`.
- openalex.py: code read `paper.get("inverted_index")`; real OpenAlex
  field (confirmed against OpenAlex docs) is `abstract_inverted_index`.
  abstract_text was always empty — entity_type classification always
  fell through to "Epidemiological" and no treatment/`treats`
  relationships were ever created from OpenAlex data. Fixed.
- openalex.py: region entity's `EntitySource` was only appended the
  first time a region was seen per run — undercounting evidence_count.
  Dedented so every paper contributes a source, matching the
  disease/treatment entity pattern.

**Why:** All four caught by verifying real API output/docs instead of
trusting assumed field names — same principle that caught the earlier
"Niger"/"Nigeria" and continent-field bugs.

**Rules out:** Nothing architectural — bug fixes within the existing
extract/transform/load pattern, no design changes.

**Unblocks:** ChEMBL and OpenAlex can be re-run with meaningfully
different, correct output. Worth auditing existing OpenAlex-sourced
entities first: `SELECT entity_type, COUNT(*) FROM entities WHERE
contributor = 'OpenAlex' GROUP BY entity_type` — likely skewed 100%
Epidemiological pre-fix.


### 2026-07-21 — Inference layer: plain Python rule functions, not DL/Datalog

**Decided:** Layer 2/3 reasoning is implemented as hand-written Python
functions performing typed graph-edge composition over
entity_relationships — not a Description Logic reasoner (owlready2)
or a Datalog engine (pyDatalog/ASP). Each rule is a plain function:
pattern of existing relationship rows in, new derived relationship
row out.

Confidence for derived facts uses a continuous score alongside the
existing discrete tier:
- `TIER_SCORE = {1: 0.3, 2: 0.6, 3: 1.0}` (Traditional/Emerging/Established)
- `combined = min(score(premise_a), score(premise_b))` — a chain is
  only as strong as its weakest premise
- `derived_score = combined * (DECAY ** depth)`, `DECAY = 0.75` global
  constant, `depth = max(premise_a.depth, premise_b.depth) + 1`
- Score maps back to a tier for storage/display (`>=0.7 → 3`,
  `>=0.4 → 2`, else `1`), but a derived fact's tier can never exceed
  `min(premise tiers)` regardless of score — hard cap against
  confidence laundering across chains.

Cycle/runaway protection, three independent guards:
- `MAX_DEPTH = 3` global constant — facts at max depth aren't used
  as premises for further derivation
- Each derived fact stores `derived_from: list[fact_id]`; before
  insert, ancestry is walked backward to reject a new
  `(subject, relation, object)` that already appears upstream
- Dedup check on `(subject, relation, object)` before any insert,
  observed or derived, as a backstop against duplicate rows

**Why:** Sankofa's relationship types (causes, treats, inhibits,
prevalent_in...) are directed weighted edges, not is-a/category
relationships — DL's classification/subsumption machinery doesn't
fit the data. Datalog/general rule engines solve a more general
problem than the fixed, small set of composition patterns Sankofa
actually needs. Owning the reasoning layer outright also avoids
locking into a formalism that may not survive Layer 4 (Ùmà,
indigenous-knowledge reasoning), which likely won't map cleanly onto
classical DL categories anyway.
**Rules out:** owlready2 (Description Logic reasoner) — rejected,
built for is-a/category hierarchies Sankofa doesn't have. Datalog/ASP
(pyDatalog, clingo) — rejected as more general/complex than needed.
SymPy — out of scope, that's for the mathematics domain, not relational
inference.
**Unblocks:** Layer 2 rule functions can be written directly against
the existing entity_relationships schema — first rule to implement:
`inhibits + causes → treats` (derived), tested on the malaria/anemia
slice before generalizing to a rule-registration framework.


### 2026-07-19 — Recursive CTE reasoning engine: dumb traversal, Python interpretation, cycle/depth/row guards

**Decided:** The Computational Symbolic Engine (Layer 2) multi-hop reasoning uses a recursive CTE
(`WITH RECURSIVE`) over `entity_relationships` that returns raw
hop-by-hop paths only (entity IDs, relationship IDs, per-hop confidence)
— no interpretation happens in SQL. Cycle protection via a visited-
entity-ID array is mandatory. Depth is a parameterized argument
(default 4), not hardcoded. Total output rows get a hard `LIMIT`.
`entity_relationships.from_entity_id` and `.to_entity_id` get indexed.
Path-level confidence is computed in Python as `MIN()` across hops.

**Why:** Mirrors the existing `load()`-stays-generic /
`transform()`-owns-meaning pattern — one place should own
interpretation, not split across SQL and Python. Fan-out from
well-connected entities (e.g. malaria, already touched by 4+
relationship types across 4 pipelines) grows combinatorially with
depth, so a row cap matters independently of the depth cap.

**Rules out:** Rule-table-driven SQL pruning (filtering
relationship-type sequences inside the CTE's join condition itself)
for this phase — deferred, gated on a relationship-type validity rule
table that doesn't exist yet.

**Unblocks:** The recursive CTE query can now be built — parameterized
depth, row-capped, cycle-guarded.



### 2026-07-18 — SL4 architecture documented

**Decided:** Full architecture written to `SL4_ARCHITECTURE.md` in project root.
Includes: CTE query patterns (single-hop, 2-hop recursive, bidirectional, path-finding),
Python evidence-weighing layer, contradiction detection, three-state epistemic resolution,
API router endpoints, coverage registry schema, and file structure for `computation/` module.

**Status:** Design phase. Phase 1 (single-hop CTEs + evidence weighing) is the minimum viable engine.

### 2026-07-18 — Pseudocode-first enforced for assistant interactions

**Decided:** The assistant provides architecture decisions, pseudocode, and
file-level guidance only. The developer types all real code by hand — no
copy-pasting generated code into the codebase.

**Why:** Writing code directly bypasses the developer's own working method
(CONTEXT.md §11), which requires understanding every line by typing it
manually. Direct code generation produces working results but skips the
comprehension and muscle-memory build that the pseudocode-first process
was designed for.

**Rules out:** The assistant writing complete files directly. The assistant
editing ingestion/model/migration code directly.

**Unblocks:** Consistent working method across all sessions going forward.

### 2026-07-18 — Staged approach: CTEs permanent, logic layer optional and deferred

**Decided:** Postgres recursive CTEs + plain Python are the engine's permanent
foundation, not a placeholder. A logic-programming layer (pyDatalog or
kanren, tool choice deferred) may be added later, on top of that
foundation, only for reasoning that genuinely needs it (e.g. Ùmà, or
open-ended analogical reasoning) — not as a replacement for the core.
**Why:** Decouples two separate questions that kept getting tangled: "is
the core reasoning engine correct" (yes — bounded, predictable
traversal, settled independent of any library's maintenance status) vs.
"is a specific optional add-on library worth adding later" (an open
question, revisited when that phase actually starts).
**Update:** pyDatalog's own repo README (v0.22.4, tests passing) confirms
maintenance was restarted June 2026, prompted by the project passing 300
GitHub stars — verified directly against the source, not secondhand.
This reopens it as a fair candidate alongside kanren for the future
layer, but does not change the core decision, since that was based on
unification/backtracking search being unpredictable for live query-serving,
a property of execution model, not maintenance status.
**Rules out:** Nothing further needs deciding on this topic until the
Ùmà layer or a genuinely open-ended reasoning query is actually being
scoped.
**Unblocks:** Engine build proceeds with no outstanding tooling questions.



### 2026-07-18 — Engine built on Postgres recursive CTEs + plain Python, not a logic-programming engine

**Decided:** The Computational Symbolic Engine (Layer 2) multi-hop traversal uses Postgres `WITH RECURSIVE` CTEs.
Contradiction detection and three-state resolution (known / knowably-absent /
uncharted) are implemented as plain Python functions operating on query
results, not as a rule engine.
**Why:** Recursive CTEs are Datalog's core mechanism (SQL + recursivity),
already running inside infrastructure chosen for scalability, with zero new
dependency. The full query catalog (single-hop, fixed 2-hop chains, evidence
weighing, contradiction checks, three-state checks) is bounded, fixed-shape
traversal — it does not require an open-ended reasoning engine.
**Rules out:** pyDatalog (GitHub repo itself currently states "not
maintained, use at your own risk," last tested against SQLAlchemy 0.7 vs.
current 2.0.41). Full Prolog/pyswip (unification-based backtracking search
is computationally unpredictable — the reason Wolfram Language and
production Datalog engines like CodeQL/Soufflé deliberately avoid it for
query-serving roles). A custom-built query language (Wolfram-scale
engineering cost, no added reasoning power over what's already decided
here).
**Unblocks:** Engine build can proceed without further tooling evaluation.


### 2026-07-18 — entity_sources / relationship_sources need author + title fields

**Decided:** Both `entity_sources` and `relationship_sources` will gain
`source_author` and `source_title` columns (nullable — not every source
type has these, e.g. WHO GHO statistical indicators).
**Why:** PubMed and OpenAlex API responses already contain this data during
`extract()`; it was being dropped before reaching `load()`. Litsi's
structured-answer object needs full citation data (paper + author, not just
a source name and URL) to produce publication-usable attributions.
**Rules out:** A backfill migration against existing source rows — decided
against in favor of a full database truncate and clean re-ingestion instead
(see wiki notes for the step-by-step).
**Unblocks:** Once ingestions are updated to pass this data through, Litsi's
structured object and the research-notebook/article feature both become
possible.


### 2026-07-17 — ChEMBL load()/transform() rewritten to match real schema; entity dedup key decided per-pipeline

**Decided:**
- ChEMBL's load() rewritten against the real models (EntityRelations/entity_relations,
  RelationshipSource.relationship_id, no internal_id field anywhere).
- ChEMBL entity dedup key: normalized (lowercased, trimmed) name + domain (exact).
  entity_type deliberately excluded from the dedup key.
- WHO's dedup key (name only, no normalization) is NOT being touched or backported -
  it's a working, statistical pipeline and stays as-is.
- Normalization (lowercase+trim) is scoped to ChEMBL only for now. NOT retrofitted
  into WHO/OpenAlex/PubMed.
- New entity_type introduced: "Molecule" (for ChEMBL compounds) - not previously in
  the documented entity_type list (Epidemiological, Clinical, Indigenous, Biological,
  Institutional, Country, Continent, region).
- ChEMBL relationship sourcing follows the OpenAlex/PubMed pattern exactly
  (source_url/source_name/confidence/context live directly on each relationship_dict,
  RelationshipSource created inline in the same loop as EntityRelations) - not a
  separate sources-list-with-composite-key-relookup design (an earlier, discarded
  draft).

**Why:** entity_type was excluded from ChEMBL's dedup key because the same disease
can already carry different entity_type values across OpenAlex ("Clinical" vs
"Epidemiological" vs "Indigenous", assigned per-paper by determine_entity_type())
- including it in the match would fragment evidence_count across rows that
represent the same real-world entity. WHO was left alone because it already works
in production and this session's principle was fixing what's broken, not touching
what isn't.

**Known, deliberately unresolved issue (not fixed, just documented):** WHO's disease
entities use domain="epidemiology"; OpenAlex/PubMed use domain="healthcare" for the
same disease names. WHO's dedup query has no domain filter (matches on name alone),
but OpenAlex/PubMed's does. This means: if WHO creates a disease entity first, a
later OpenAlex/PubMed run will NOT find it (domain mismatch) and will create a
second row under the same name. The reverse order does not duplicate (WHO's
name-only check finds whatever already exists). Given WHO ran first historically,
this likely already exists in the live DB for some diseases. Not fixed - deferred,
same as the WHO dedup-key decision above. Worth a one-time audit query later:
`SELECT name, domain, COUNT(*) FROM entities GROUP BY name, domain HAVING COUNT(DISTINCT domain) > 1`.

**Rules out:** entity_type in ChEMBL's entity dedup filter. A separate
sources-list/composite-key-relookup architecture for relationship sourcing.

**Unblocks:** ChEMBL's transform()/load() are code-complete and were about to be
tested, but ChEMBL's own drug_indication API endpoint is returning HTTP 500 (server
side, confirmed via curl - not a code issue, not filter-specific, reproduces with
or without mesh_id). Blocked externally, not by any Sankofa-side bug. Check
http://chembl.github.io/status/ before resuming. No further ChEMBL ingestion work
until that clears.

**Next:** Move to Computational Symbolic Engine (Layer 2) while ChEMBL is
externally blocked - per roadmap, this was next after ingestion regardless.


### 2026-07-16 — ChEMBL load() rewritten to match real schema (EntityRelations, no internal_id, normalized entity dedup)

**Decided:** The ChEMBL load() pseudocode was rewritten to match the real
SQLAlchemy models: the relationship table is EntityRelations (not
"Relationship"), relationship_id resolves via GET_OR_CREATE against
RelationshipType instead of being stored as a string, source-to-relationship
linking uses the (from_entity_id, to_entity_id, relationship_type_id)
composite key instead of an invented internal_id column, and Entity dedup
matches on normalized (lowercased, trimmed) name + entity_type instead of
exact-string name.
**Why:** The original pseudocode was drafted against an imagined schema
instead of the real models (models/entities.py, models/entity_relations.py),
causing a wrong table/class name, a nonexistent internal_id column, and
entity fields that don't exist. Entity.name also has no DB-level unique
constraint, and WHO/OpenAlex/PubMed/ChEMBL don't agree on name
casing/whitespace, so exact-string dedup risked silently duplicating
entities and fragmenting evidence_count across rows — undermining the §5
evidence-weighing design.
**Rules out:** Exact-string entity name matching for dedup. Transient
internal_id attributes on ORM objects for linking sources to relationships.
**Unblocks:** ChEMBL load() can be finalized once Gemini's corrected
pseudocode is reviewed. The normalized-name dedup rule applies to all
ingestions going forward, not just ChEMBL.


### 2026-07-14 — Sankofa funding, team, and governance model locked

**Decided:** Sankofa is funded via grants as the default path, with revenue (institutional subscriptions, licensing) as the second pillar. Equity investment is a last resort only, evaluated solely if grants + revenue together aren't enough — and dropped immediately once revenue is flowing. Team stays solo until explicitly signaled otherwise; when hiring starts, priority goes to a business/ops co-founder or hire over a second technical role. CONTEXT.md itself is the company's governance mechanism — no separate governance structure exists or is planned.

**Why:** Preserves full ownership and mission control as long as possible; avoids diluting the "competence and problem-solving first" principle with investor pressure before it's necessary.

**Rules out:** Pursuing investment in parallel with grants/revenue as a default strategy. A separate formal governance structure beyond the existing decision log.

**Unblocks:** Grant research and applications can proceed as the primary funding motion starting Phase 2/3 of the 10-year plan without a parallel investment track to manage.

### 2026-07-13 — Build in public, starting now

**Decided:** Share Sankofa progress publicly as it's built, rather than waiting for a finished product before creating any awareness.

**Why:** Advice from a friend with two shipped products, from direct experience — waiting until "done" to start building an audience costs real time and momentum that can't be recovered later.

**Rules out:** Silent build-then-launch approach.

**Unblocks:** A running content/posting queue can now be drawn from real build milestones (evidence-weighing redesign, ChEMBL debugging, engine design calls, etc.) whenever the developer is ready to post.

**Note:** this is about visibility and audience-building, not user distribution — the §8 "narrow before broad" plan for onboarding actual researchers (warm introductions, not public launch) still stands. Building in public grows awareness of the project; it doesn't mean opening the product itself to broad use before the query engine exists.
