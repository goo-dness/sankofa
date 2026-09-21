# Sankofa — ISSUE_LOG.md

Running log of issues found in the Sankofa code and data, written the same way as the decision log in `CONTEXT.md`. One entry per issue, dated, with a plain-word name. Newest entries go on top. An entry is written only after the issue has been checked against real data, and it is updated with the fix and the proof once it is fixed.

---

### 2026-09-21 — fake-contradictions

**Found:** while checking the genetic data Grok added on Sep 20. Every term in `DUAL_GENETIC_TERMS` (`openalex.py` around line 1085, `pubmed.py` around line 652) wrote both `protective_against` and `predisposes_to` from the same term to the same disease. The word matching only sees that a term appears in an abstract, so it cannot tell which direction is true, and a contradiction was created every time. Checked against `sankofa_db`: 10 entity pairs carried both types. Five were for malaria (G6PD deficiency, glucose-6-phosphate dehydrogenase deficiency, hemoglobin c, hbs, sickle cell trait). The other five were `hemoglobin s` and `hbs` to sickle cell disease, `alpha thalassaemia` and `beta thalassaemia` to thalassaemia, and `glucose-6-phosphate dehydrogenase deficiency` to G6PD deficiency. The malaria neighborhood query reported 5 contradictions. Severity was high, because `contradictions.py` was working correctly and reported them as real.

**Fixed:** Option A, neutral by default and direction only from a curated table. The genetic block in `openalex.py` and `pubmed.py` now writes `associated_with`, and `DUAL_GENETIC_TERMS` is deleted. Directed facts now come only from `data/genetic_associations.py`, loaded by `ingestions/curated_genetics.py` through `run_curated_genetics()` in `seed.py`. A row without a source is skipped, and no coverage is recorded for those two types on purpose, because the table only covers verified pairs. The old scan-made rows were removed with `scripts/remove_scan_genetics.py` (56 relationships, 451 source rows, 16 coverage rows), and the OpenAlex scan was re-run to fill `associated_with`.

**Why:** a term appearing in an abstract cannot show direction, and a wrong direction is worse than none. Direction now belongs to a checked (factor, disease) pair with a real citation, not to a factor alone.

**Verified:** `associated_with` has 46 rows, which matches the 46 `protective_against` rows that were removed. `protective_against` and `predisposes_to` have none. The malaria neighborhood reports 0 contradictions (it was 5). The curated loader test skipped all 5 table rows with "no source yet" and wrote nothing.

**Rules out:** inferring direction from a term's presence in an abstract.

**Not part of this fix:** the table has no verified rows yet, so no directed facts exist until sources are checked and added. The PubMed scan was changed the same way but has not been re-run.

**Status:** FIXED on 2026-09-21.
