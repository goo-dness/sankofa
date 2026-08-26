# run_causal_path.py — project root, not inside computation/
from app.database import get_db
from computation.rules import causal_path

with get_db() as db:
    causal_path(db)
