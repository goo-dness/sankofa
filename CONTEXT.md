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

### Long-Term Domain Scope

Healthcare is the first domain — not the only one. Sankofa's long-term ambition is breadth comparable to Wolfram Alpha's. Confirmed directly against Wolfram Language's own Documentation Center category list (screenshotted June 2026) as a reference point for the scale of "computational knowledge engine":

Core Language & Structure, Data Manipulation & Analysis, Visualization & Graphics, Machine Learning & LLMs, Symbolic & Numeric Computation, Higher Mathematical Computation, Strings & Text, Graphs & Networks, Images, Geometry, Sound & Video, Knowledge Representation & Natural Language, Time-Related Computation, Geographic Data & Computation, Scientific and Medical Data & Computation, Engineering Data & Computation, Financial Data & Computation, Social, Cultural & Linguistic Data.

Domains explicitly named for Sankofa's own expansion, beyond healthcare: general medicine, mathematics, biology, chemistry, economics, astronomy, space science — with more still to be scoped as the project matures.

This is a long-term expansion target, not a near-term build item. Healthcare remains the proving ground — the ingestion pattern, the evidence-weighing system (§5), the relationship-type vocabulary approach, and the eventual SL4 query engine are all being built here first specifically so they generalize cleanly to these other domains later, rather than being healthcare-specific one-offs.

---

## 2. Project Structure (locked, flat)

```
sankofa/
├── main.py
├── app/
│   ├── database.py
│   ├── config.py
│   └── http_utils.py     (shared get_with_retry — used by every ingestion)
├── models/
│   ├── entities.py
│   ├── entity_names.py
│   ├── entity_relationships.py
│   ├── entity_sources.py
│   ├── entity_people.py
│   ├── relationship_sources.py
│   └── relations_type.py
├── schemas/              (mirrors models, ConfigDict from_attributes=True)
├── routers/
│   └── entities.py       (no crud.py — routers handle DB ops directly)
├── data/
│   ├── relationship_types.py
│   └── seed.py           (owns all orchestrator functions — run_who(), run_openalex(), run_pubmed())
├── ingestions/
│   ├── who.py
│   ├── openalex.py
│   ├── pubmed.py         ✅ complete
│   └── chembl.py         ✅ complete
└── migrations/           (Alembic)
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
No further new data sources after ChEMBL. Europe PMC was on the original roadmap but has been deliberately dropped — the priority now is finishing ChEMBL and moving straight into the SL4 query engine (pyDatalog). Ethnomedicine-focused ingestion (§7) remains the identified strategic gap but is explicitly deferred past the query engine, not before it — "build fast" means no more dataset detours until there's a working reasoning layer.

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

## 9. SL4 Query Engine — Formal Design Requirement (not yet built)

**Requirement: Three-state epistemic awareness.**

A human expert distinguishes three states of knowledge; Sankofa's query engine must too:

1. **Known** — a relationship exists, backed by ≥1 source. Return it with confidence tier and evidence_count.
2. **Knowably absent** — the domain was ingested, nothing was found. Say so explicitly: "no established relationship found."
3. **Uncharted** — the domain hasn't been ingested yet. Say so explicitly, distinct from state 2 — this is a coverage gap, not a negative finding.

Without this distinction, an empty query result is ambiguous — a researcher can't tell if Sankofa looked and found nothing, or never looked at all. This makes the system unreliable for real research use.

**Implementation note:** `evidence_count = 0` cannot currently exist by design (relationships only get created when evidence exists), so absence-in-graph already correctly means "no evidence found during ingestion." The query engine needs to surface this classification explicitly at answer time, not just return empty.

**Future dependency:** fully distinguishing state 2 from state 3 will eventually require a coverage registry — a record of which domains/diseases/sources have actually been ingested. Deferred until after SL4's first working version, but the response structure should be designed to accommodate it later.

---

## 10. Roadmap

**Immediate (locked, no further additions):** ChEMBL ingestion → straight into the SL4 query engine. PubMed is done; Europe PMC has been deliberately dropped from the plan; ethnomedicine-targeted ingestion is deferred until after the query engine exists, not before.

**Current status (July 2026):** paused on heavy implementation to close a foundational gap — working through Charles Petzold's *Code* to understand what Python and the underlying hardware are actually doing, rather than continuing to translate pseudocode into syntax without full comprehension. Still coding in small amounts (bug fixes, small additions) during this period, not fully stopped. This directly feeds the eventual C/CPython-internals work needed for OpenShark later — not a detour from the long-term arc, front-loaded foundation for it.

**After ChEMBL:** SL4 query engine — symbolic reasoning layer, pyDatalog. This is where the three-state epistemic awareness requirement (§9) gets implemented, and where confidence/evidence_count actually get *used* in synthesized answers rather than just stored.

**After the query engine:** frontend, then Litsi — the AI layer (RAG pipeline connecting Claude API to PostgreSQL), kept architecturally distinct from Sankofa's symbolic core. Embeddings belong to Litsi, not to Sankofa's computation engine — this separation is deliberate and must be maintained.

**Long-term (5-company, 10-year arc):** Space Catalog (deployed) → Sankofa Engine (active) → Litsi → OpenShark/Atax LLM Runtime (C, hardware-agnostic AI inference runtime, 2027–2028+) → embedded/chip-level work.

---

## 11. Working Method (how this project gets built)

- **Pseudocode-first, real code only on request.** Logic gets planned and reviewed in a consistent pseudocode style (ALL CAPS actions, `//` comments, FUNCTION/END FUNCTION) before any real code is written, so the developer types every line by hand and understands it — no copy-pasting, ever.
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

### 2026-07-18 — SL4 architecture documented

**Decided:** Full SL4 architecture written to `SL4_ARCHITECTURE.md` in project root.
Includes: CTE query patterns (single-hop, 2-hop recursive, bidirectional, path-finding),
Python evidence-weighing layer, contradiction detection, three-state epistemic resolution,
API router endpoints, coverage registry schema, and file structure for `app/sl4/` module.

**Status:** Design phase. Phase 1 (single-hop CTEs + evidence weighing) is the minimum viable SL4.

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

**Decided:** Postgres recursive CTEs + plain Python are SL4's permanent
foundation, not a placeholder. A logic-programming layer (pyDatalog or
kanren, tool choice deferred) may be added later, on top of that
foundation, only for reasoning that genuinely needs it (e.g. Ùmà, or
open-ended analogical reasoning) — not as a replacement for the core.
**Why:** Decouples two separate questions that kept getting tangled: "is
the SL4 core reasoning engine correct" (yes — bounded, predictable
traversal, settled independent of any library's maintenance status) vs.
"is a specific optional add-on library worth adding later" (an open
question, revisited when that phase actually starts).
**Update:** pyDatalog's own repo README (v0.22.4, tests passing) confirms
maintenance was restarted June 2026, prompted by the project passing 300
GitHub stars — verified directly against the source, not secondhand.
This reopens it as a fair candidate alongside kanren for the future
layer, but does not change the SL4-core decision, since that was based on
unification/backtracking search being unpredictable for live query-serving,
a property of execution model, not maintenance status.
**Rules out:** Nothing further needs deciding on this topic until the
Ùmà layer or a genuinely open-ended reasoning query is actually being
scoped.
**Unblocks:** SL4 build proceeds with no outstanding tooling questions.



### 2026-07-18 — SL4 built on Postgres recursive CTEs + plain Python, not a logic-programming engine

**Decided:** SL4's multi-hop traversal uses Postgres `WITH RECURSIVE` CTEs.
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
**Unblocks:** SL4 build can proceed without further tooling evaluation.


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

**Next:** Move to SL4 / pyDatalog symbolic reasoning layer while ChEMBL is
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

**Unblocks:** A running content/posting queue can now be drawn from real build milestones (evidence-weighing redesign, ChEMBL debugging, SL4 design calls, etc.) whenever the developer is ready to post.

**Note:** this is about visibility and audience-building, not user distribution — the §8 "narrow before broad" plan for onboarding actual researchers (warm introductions, not public launch) still stands. Building in public grows awareness of the project; it doesn't mean opening the product itself to broad use before the query engine exists.
