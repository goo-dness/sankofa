from app.database import get_db
from computation.executor import execute_two_hop_forward

with get_db() as db:
    print("--- Branch (a): hop1 uncovered ---")
    result = execute_two_hop_forward(db, "buruli ulcer", "activates", "treats")
    print(result["epistemic_state"])

    print("\n--- Branch (b): hop1 covered, empty ---")
    result = execute_two_hop_forward(db, "cholera", "treats", "treats")
    print(result["epistemic_state"])

    print("\n--- Branch (c): hop2 uncovered ---")
    result = execute_two_hop_forward(db, "Malaria Est Incidence ZAF 2019", "measures", "protective_against")
    print(result["epistemic_state"])

    print("\n--- Branch (d): all covered, empty ---")
    result = execute_two_hop_forward(db, "Malaria Est Incidence ZAF 2019", "measures", "binds_to")
    print(result["epistemic_state"])
