from app.database import get_db
from computation.epistemic import EpistemicState
from computation.executor import execute_constraint_query
from computation.verify_claim import verify_claim

with get_db() as db:
    # --- A: extra checks (wrapper only) ---
    print("--- A1: empty source ---")
    print(verify_claim(db, "", "malaria", "treats")["epistemic_state"])

    print("--- A2: empty target ---")
    print(verify_claim(db, "artemisinin", "", "treats")["epistemic_state"])

    print("--- A3: empty relationship type ---")
    print(verify_claim(db, "artemisinin", "malaria", "")["epistemic_state"])

    # --- C: no path -> UNCHARTED ---
    print("--- C1: real entities, no constrained path --")
    r = verify_claim(db, "ivermectin", "cholera", "treats")
    print(r["epistemic_state"])
    print("results length:", len(r["query_results"]))

    print("--- B1: known treats edge ---")
    r = verify_claim(db, "ivermectin", "onchocerciasis", "treats")
    print(r["epistemic_state"])
    print(r["query_results"])

    # --- E: shape checks on last KNOWN or UNCHARTED result ---
    print("--- E; shape ---")
    print("keys:", sorted(r.keys()))
    print("contradictions:", r["contradictions"])
    print("chain_weight:", r["chain_weight"])
