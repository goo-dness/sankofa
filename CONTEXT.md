# Sankofa Engine — Project Context

**Developer:** Goodness Akuba, Lagos, Nigeria. Self-taught software developer, aspiring AI systems programmer.
**Repo:** github.com/goo-dness
**Last updated:** September 2026 (synced 2026-09-23 against live state through 2026-09-22)

---

## 1. What Sankofa Is

Sankofa is a computational knowledge platform for Africa. The reference point is Wolfram Alpha, but African-centred: **symbolic reasoning over a knowledge graph — not RAG, not CRUD.**

The core complaint Sankofa exists to answer: general-purpose tools like Wolfram Alpha, when pushed into a specific domain like African health research, degrade into returning lists of papers instead of computed answers. A real user — a microbiology/biostatistics PhD student at Covenant University, Sankofa's first target user — described exactly this: she asked Wolfram a health question and got back sources to dig through herself, the same failure mode as a RAG chatbot. Sankofa's job is to have already done that digging, weighed the evidence, and return a synthesized, sourced, confidence-rated answer.

**North star:** _Sankofa should reason like a human does._ Not just retrieve facts, but chain them together, weigh evidence instead of collecting it uncritically, and know the difference between "this is false," "this is unknown," and "this hasn't been looked at yet."

**First domain:** Healthcare.

### Sankofa Engine — Layers

| Layer | Name                          | Status         | What it does                                                                                                                                                                                                           |
| ----- | ----------------------------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | Knowledge Foundation          | ✅ Complete    | Data ingestion and database. WHO, OpenAlex, PubMed, ChEMBL pipelines. Entities and relationships, confidence tiers, evidence weighing.                                                                                 |
| 2     | Computational Symbolic Engine | 🔄 In progress | Recursive CTEs + plain Python. Epistemic three-state, contradiction detection, and weigh_chain done; two-hop epistemic partial; causal_path rule implemented (2026-08-25); neighborhood epistemic design still open.   |     |
| 3     | AI Layer (Litsi)              | ⏳ Next        | Interprets and explains what the engine computes. RAG pipeline connecting Claude API to PostgreSQL. Architecturally distinct from the symbolic core — embeddings belong to Litsi, not to Sankofa's computation engine. |
| 4     | Ùmà Layer                     | 🔮 Final       | Formalizes indigenous knowledge as computable reasoning. May use a logic-programming layer (pyDatalog or kanren) on top of the CTE foundation.                                                                         |

### Long-Term Domain Scope

Healthcare is the first domain — not the only one. Sankofa's long-term ambition is breadth comparable to Wolfram Alpha's. Confirmed directly against Wolfram Language's own Documentation Center category list (screenshotted June 2026) as a reference point for the scale of "computational knowledge engine":

Core Language & Structure, Data Manipulation & Analysis, Visualization & Graphics, Machine Learning & LLMs, Symbolic & Numeric Computation, Higher Mathematical Computation, Strings & Text, Graphs & Networks, Images, Geometry, Sound & Video, Knowledge Representation & Natural Language, Time-Related Computation, Geographic Data & Computation, Scientific and Medical Data & Computation, Engineering Data & Computation, Financial Data & Computation, Social, Cultural & Linguistic Data.

Domains explicitly named for Sankofa's own expansion, beyond healthcare: general medicine, mathematics, biology, chemistry, economics, astronomy, space science — with more still to be scoped as the project matures.

This is a long-term expansion target, not a near-term build item. Healthcare remains the proving ground — the ingestion pattern, the evidence-weighing system (§5), the relationship-type vocabulary approach, and the eventual Computational Symbolic Engine (Layer 2) are all being built here first specifically so they generalize cleanly to these other domains later, rather than being healthcare-specific one-offs.

---

## 2. Project Structure (flat; verified against live filesystem 2026-08-10, additions since then taken from DECISIONS.md and ISSUES.md, revised 2026-09-23)

Real root is `sankofa/`, flat at repo root — no `backend/` subfolder. A `backend/` nesting briefly existed and was removed on 2026-08-10 after it started causing import errors (anything resolving `from app.database import ...` etc. needs `app/`, `models/`, `ingestions/` etc. as direct siblings of the invocation root, not nested a level deeper). `scripts/` also sits at repo root, alongside everything else, not inside any subfolder.

```
sankofa/                    (repo root)
├── README.md
├── main.py
├── alembic.ini
├── requirements.txt
├── CONTEXT.md
├── SL4_ARCHITECTURE.md
├── DECISIONS.md              (dated decision log, newest first)
├── ISSUES.md                 (dated issue log, newest first)
├── .env / .env.example
├── app/
│   ├── database.py
│   ├── config.py
│   └── http_utils.py     (shared get_with_retry — used by every ingestion)
├── models/
│   ├── entities.py
│   ├── entity_names.py
│   ├── entity_relationships.py    (EntityRelations — has derived_from/derivation_depth, see DECISIONS.md 2026-08-01)
│   ├── entity_sources.py
│   ├── entity_people.py
│   ├── relationship_sources.py
│   ├── relations_type.py
│   └── coverage.py       (IngestionCoverage — relationship_type-granular, see DECISIONS.md 2026-08-01)
├── schemas/               (mirrors models 1:1, ConfigDict from_attributes=True — entities, entity_names, entity_people, entity_relationships, entity_sources, relations_type, relationship_sources)
├── routers/               (mirrors models 1:1, one router per table — entities, entity_names, entity_people, entity_relationships, entity_sources, relations_type, relationship_sources; no engine.py yet, planned for Layer 2 API per SL4_ARCHITECTURE.md §6)
├── computation/           (Computational Symbolic Engine — Layer 2)
│   ├── __init__.py
│   ├── queries.py         (CTE SQL queries)
│   ├── executor.py        (execute_single_hop, execute_two_hop, etc.)
│   ├── weighing.py        (aggregate_confidence, aggregate_evidence, weigh_chain, weigh_derived_fact)
│   ├── contradictions.py  (detect_contradictions, CONFLICT_PAIRS)
│   ├── epistemic.py       (resolve_epistemic_state, has_coverage, resolve_chain_epistemic_state_forward/backward, EpistemicState enum)
│   └── rules.py           (Layer 2/3 derivation rules — causal_path implemented and verified 2026-08-25, see DECISIONS.md)
├── data/
│   ├── relationship_types.py
│   ├── genetic_associations.py   (hand-verified genetic factor→disease pairs with citations; a row without a source is skipped — DECISIONS.md 2026-09-21)
│   └── seed.py           (owns all orchestrator functions — run_who_ingestion(), run_openalex(), run_pubmed(), run_chembl(), run_curated_genetics(), record_coverage())
├── ingestions/
│   ├── who.py
│   ├── openalex.py       ✅ complete, includes causes detection + organism name normalization (DECISIONS.md 2026-08-01, 2026-08-09)
│   ├── pubmed.py         ✅ complete, includes causes detection + organism name normalization (DECISIONS.md 2026-08-01, 2026-08-09)
│   ├── chembl.py          ✅ complete, includes expressed_by bridge (protein→organism, widened 2026-08-09) and derived_from (salt/form hierarchy, confirmed 2026-08-25)
│   └── curated_genetics.py   (loads data/genetic_associations.py into directed genetic edges; records no coverage on purpose — DECISIONS.md 2026-09-21)
├── scripts/
│   ├── cleanup_duplicates.py           (one-time — literal duplicate entities from before the unique name+domain index existed)
│   ├── normalize_causal.py             (one-time — renames/merges informal CausalAgent organism names to formal binomial names, per ORGANISM_NAME_MAP)
│   ├── dedupe_entity_relations.py      (one-time — merges duplicate entity_relations rows left over from historic entity merges, recomputes evidence_count/confidence from relationship_sources)
│   ├── remove_scan_genetics.py         (one-time, 2026-09-21 — removed the scan-made directed genetic relationships and their sources and coverage rows; see ISSUES.md "fake-contradictions")
│   └── remove_vector_as_causes.py      (one-time, 2026-09-21 — deleted the 18 vector/reservoir/host `causes` edges and their sources; see ISSUES.md)
├── migrations/            (Alembic — env.py, script.py.mako, versions/)
└── tests/                 (empty — no tests written yet)
```

---

## 3. Database Schema

**entities**
`id, name, domain, entity_type, region, original_lang, expression, confidence (int 1-3), evidence_count (int, default 1), contributor, timestamps`

**entity_relationships**
`id, from_entity_id, to_entity_id, relationship_id (FK → relationship_types), confidence (int 1-3), evidence_count (int, default 1), context, derived_from, derivation_depth, timestamps` — `derived_from` and `derivation_depth` track rule-derived facts (ancestry and depth); see DECISIONS.md.

**entity_sources**
`id, entity_id, source_name, source_url, source_author, source_title, timestamps` — provenance trail for entities. `source_author` and `source_title` are nullable (not every source has them, e.g. WHO GHO indicators); added 2026-07-18, see DECISIONS.md.

**relationship_sources** _(new — added mid-project, see §5)_
`id, relationship_id, source_name, source_url, source_author, source_title, confidence (this specific source's own rating), context, timestamps` — provenance trail for relationships, mirrors entity_sources.

**relationship_types**
Lives in the DB, not an enum. 63 seeded relationship types across 9 domains: pathology, epidemiology, pharmacology, molecular, ethnomedicine, clinical, genetics, institutional, general. Includes `causes`, `treats`, `traditionally_treats`, `prevalent_in`, `studied_by`, `protective_against`, `structurally_similar_to`, and more — see `data/relationship_types.py` for the full list.

**Other tables (not yet populated by any ingestion):** `entity_names`, `entity_people`.

**ingestion_coverage**
`id, domain, disease_name, source_name, relationship_type, last_ingested_at` — tracks which (disease, source, relationship_type) combinations have been ingested. Enables three-state epistemic awareness (§9) at relationship-type granularity. Unique constraint `uq_disease_source_reltype` on `(disease_name, source_name, relationship_type)`. Populated by each ingestion pipeline via `record_coverage()` in `data/seed.py`, once per relationship type actually touched in a run.

**Confidence tiers:** 1 = Traditional, 2 = Emerging, 3 = Established.

**Entity types in use:** Epidemiological, Clinical, Indigenous, Biological, Institutional, Country, Continent, region, Molecule (ChEMBL compounds).

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

### Genetic and vector scans (2026-09-12 to 2026-09-21)

- **2026-09-12:** the genetic/protective types (`protective_against`, `predisposes_to`, `resistant_to`) and vector/transmission types (`transmitted_by`, `vector_of`, `spreads_via`) are populated by broad vocabulary-matching in `openalex.py` and `pubmed.py`, not gated behind a Layer 2 rule (DECISIONS.md).
- **2026-09-21:** the genetic scan now writes only a neutral `associated_with` edge. Directed genetic edges come only from `data/genetic_associations.py`, loaded by `ingestions/curated_genetics.py` (`run_curated_genetics()` in `seed.py`). As of that date the table had no verified rows, so no directed genetic facts existed. The OpenAlex scan was re-run; the PubMed scan was changed the same way but not yet re-run (DECISIONS.md, ISSUES.md).
- **2026-09-21:** 18 vector, reservoir and intermediate-host terms were removed from `CAUSAL_AGENT_VOCABULARY`; they belong only in the vector list (ISSUES.md).

### Scope decision (locked)

No further new data sources after ChEMBL. Europe PMC was on the original roadmap but has been deliberately dropped — the priority now is finishing ChEMBL and moving straight into the Computational Symbolic Engine (Layer 2). Ethnomedicine-focused ingestion (§7) remains the identified strategic gap but is explicitly deferred past the engine, not before it — "build fast" means no more dataset detours until there's a working reasoning layer.

---

## 5. The Evidence-Weighing Redesign (major architectural fix)

**The problem, caught mid-project:** the original `load()` logic skipped any entity or relationship that already existed. This meant confidence got permanently frozen at whatever the _first_ paper contributed — if paper #1 was a weak case report and papers #2–50 were strong RCTs all confirming the same fact, the relationship stayed at confidence 1 forever. This directly contradicted the north star: a human's confidence in a claim grows as independent evidence accumulates: this system's didn't.

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

Of the 63 relationship types already seeded, six are ethnomedicine-specific and **currently have zero data feeding them**: `traditionally_treats`, `corresponds_to`, `documented_in`, `practiced_by`, `contains`, `prepared_as`.

This is deliberately identified as Sankofa's actual point of differentiation. WHO GHO exists. OpenAlex exists. Nobody has built a confidence-tiered, queryable, evidence-weighed graph of African traditional medicine at scale. This is the gap that makes Sankofa not-just-another-Wolfram-Alpha.

The genetic/protective layer and the vector/transmission layer have been populated by vocabulary scans since 2026-09-12 (see §4). Directed genetic facts (`protective_against`, `predisposes_to`) come only from a hand-verified table, which had no verified rows as of 2026-09-21.

**Order:** PubMed and ChEMBL are done. Europe PMC was dropped (§4 scope decision). The dedicated ethnomedicine-targeted ingestion pass is deferred until after the reasoning layer (§10).

---

## 8. Business Model & Distribution

**The core pricing logic:** Sankofa does not sell facts — every underlying source (WHO GHO, OpenAlex, PubMed, eventually ChEMBL) is free and public. What Sankofa sells is the _time_ a researcher would otherwise spend finding, cross-referencing, and weighing all of that themselves. Same model as Wolfram Alpha Pro: the math was never scarce, the computation and synthesis is what people pay for. Confidence tiers and `evidence_count` aren't just architecture — they're the visible receipt proving the synthesis work was actually done, which is the entire monetization argument made concrete.

**Three product surfaces, mapped to what's actually worth paying for:**

- **Query Interface** — likely stays free. Charging just to _ask_ a question when the raw evidence is public contradicts Sankofa's own "accessible, African price points" positioning, and is what gets first users like the Covenant University researcher in the door.
- **Research Notebook + assistant** — the primary paid surface. Value is saved time and a structured working environment around computed answers, not exclusive access to facts.
- **Community / Learning Centre** — mentorship and researcher connection is the one truly scarce resource (people's time and attention, unlike facts, isn't abundant); freemium for learning content.

**Distribution — narrow before broad, deliberately:** with no finished query engine yet, broad launch would mean users hitting an unfinished product — hard to undo once that story spreads. Current plan is finding 4–5 more researchers like the validated Covenant University contact through warm introductions (her supervisor, her department, her research networks) rather than public launch channels. Explicitly rejecting hype-driven "check out my app" distribution culture (WhatsApp founder groups, launch-day noise) in favor of quiet, evidence-backed credibility — slower, but matches Sankofa's actual differentiator.

**Comparison worth remembering:** Claude Science (Anthropic, launched June 2026) pulls from the same public sources (PubMed, OpenAlex among its 60+ connected databases) but produces session-bound artifacts for one researcher's one project — no persistent, evidence-weighted fact that compounds in value the way a Sankofa entity does. Confirms the "time, not access" model is sound, but is a personal productivity tool, not a competing knowledge graph.

---

## 9. Computational Symbolic Engine (Layer 2) — Formal Design Requirement (implemented in `computation/epistemic.py`)

**Requirement: Three-state epistemic awareness.**

A human expert distinguishes three states of knowledge; Sankofa's query engine must too:

1. **Known** — a relationship exists, backed by ≥1 source. Return it with confidence tier and evidence_count.
2. **Knowably absent** — the domain was ingested, nothing was found. Say so explicitly: "no established relationship found."
3. **Uncharted** — the domain hasn't been ingested yet. Say so explicitly, distinct from state 2 — this is a coverage gap, not a negative finding.

Without this distinction, an empty query result is ambiguous — a researcher can't tell if Sankofa looked and found nothing, or never looked at all. This makes the system unreliable for real research use.

**Implementation note:** `evidence_count = 0` cannot currently exist by design (relationships only get created when evidence exists), so absence-in-graph already correctly means "no evidence found during ingestion." The query engine needs to surface this classification explicitly at answer time, not just return empty.

**Coverage registry:** the `ingestion_coverage` table (§3) tracks which (disease, source, relationship_type) combinations have been ingested, enabling full three-state epistemic awareness. Each pipeline writes a row via `record_coverage()` in `data/seed.py`.

---

## 10. Roadmap

**Immediate (locked):** Harden and complete the Computational Symbolic Engine (Layer 2). All four ingestion pipelines are done; Europe PMC remains deliberately dropped; ethnomedicine-targeted ingestion stays deferred until after a solid reasoning layer. Current open Layer 2 items include full two-hop epistemic awareness, `execute_neighborhood` epistemic design, and further rule work beyond `causal_path`. Parallel data-quality work continues on already-seeded types (curated genetic sources, any residual vocabulary issues).

**After the engine is query-ready:** frontend, then Litsi (Layer 3) — the AI layer (RAG pipeline connecting Claude API to PostgreSQL), kept architecturally distinct from the symbolic core. Embeddings belong to Litsi, not to the computation engine — this separation is deliberate and must be maintained.

**Long-term (5-company, 10-year arc):** Space Catalog (deployed) → Sankofa Engine (active) → Litsi → OpenShark/Atax LLM Runtime (C, hardware-agnostic AI inference runtime, 2027–2028+) → embedded/chip-level work.
---

## 11. Working Method (how this project gets built)

Locked collaboration rules (corrected 2026-09-22). Model-agnostic — same ownership and sequence whether the primary or a backup tool is used.

- **State lives in CONTEXT.md, DECISIONS.md and ISSUES.md.** Always read these first. Do not ask for re-explanation of settled state.
- **Ownership split.** Human owns goals, problem definitions, assumptions, architectural decisions, domain models, research conclusions, acceptance criteria, final decisions, and understanding of important mechanisms. AI handles research, verification, criticism, exploration, approved implementation, boilerplate, refactoring, tests, debugging assistance, documentation, and mechanical editing.
- **Problem-solving sequence:** define → explore → challenge → decide → specify → implement → review → real test → observe → debug → verify → state updated. Never implement merely because a plausible solution exists.
- **Code workflow (corrected 2026-09-22):**
  1. AI writes pseudocode first (ALL CAPS actions, `//` comments, FUNCTION/END FUNCTION style).
  2. Human reviews and confirms (or requests changes).
  3. Once confirmed, AI translates the approved pseudocode into real code in chat.
  4. Human retains ownership of the decision and understanding; the translation step removes wasted manual re-typing of already-understood logic.
  - New logic still starts as pseudocode. Fixes/edits to existing code are real code only when explicitly requested.
  - If implementation would require a new architectural decision that has not been made, stop and flag it — never decide silently.
- **Verify against real API output / live SQL before writing logic.** Several real bugs (missing `continent` field on OpenAlex institutions, PubMed's inconsistent MeSH tagging, the "Niger"/"Nigeria" substring bug, ChEMBL field-name mismatches) were only caught this way, not by reading documentation alone.
- **Research rule:** claim → source → verify → compare → assess evidence → conclusion. AI claims are not evidence by themselves. Distinguish fact / source-reported claim / interpretation / hypothesis / open question.
- **One issue at a time.** Secondary findings are named, checked for impact on the current task, and (if worth tracking) entered into ISSUES.md in the dated Found / Fixed / Why / Verified / Rules out / Status format.
- **Explain code line by line** when teaching or reviewing. Standing rule across sessions.
- **One clean file swap over incremental patches** when multiple interconnected bugs need fixing at once.

---

## 12. Brand Identity (locked)

**Colours:** Charcoal `#1A1A1A`, Ochre `#8B4513`, Copper `#B87333`, Gold `#C9A84C`, Ivory `#F5F0E8`, Ash `#6B6355`
**Typography:** Cormorant Garamond / Crimson Pro / Source Code Pro
**Tagline:** _"Se wo were fi na wosankofa a yenkyi."_
