from sqlalchemy import text
from sqlalchemy.orm import Session
from computation.weighing import weigh_derived_fact, MAX_DEPTH



def get_relationship_id(db, name):
    sql = text("""
        SELECT id
        FROM relationship_types
        WHERE name = :name
        LIMIT 1
        """)
    row = db.execute(sql, {"name": name}).mappings().first()
    if row is None:
        raise ValueError(f"Relationship type {name} not found")
    return row["id"]

def would_create_cycle(db, mol_id, treats_id, dis_id, premise_ids):
    # Checks whether the FACT ABOUT TO E CREATED already exists somewhere upstream in its own premises` ancestry
    target_triple = (mol_id, treats_id, dis_id)

    visited = set()
    stack = list(premise_ids)

    while stack:
        current_id = stack.pop()

        if current_id in visited:
            continue
        visited.add(current_id)

        row = db.execute(text("""
            SELECT from_entity_id, relationship_id, to_entity_id, derived_from
            FROM entity_relations
            WHERE id = :eid
            """), {"eid": current_id}).mappings().first()
        if row is None:
            continue

        current_triple = (row["from_entity_id"], row["relationship_id"], row["to_entity_id"])
        if current_triple == target_triple:
            return True

        if row["derived_from"] is not None:
            for ancestor_id in row["derived_from"]:
                stack.append(ancestor_id)
    return False

def causal_path(db):
    treats_id = get_relationship_id(db, "treats")

    candidate_sql = text("""
        WITH
        inh AS (
            SELECT er.id AS inh_id, er.from_entity_id AS mol_id, er.to_entity_id AS prot_id, er.confidence AS inh_conf, er.derivation_depth AS inh_depth, er.derived_from AS inh_from
            FROM entity_relations er
            JOIN relationship_types rt ON er.relationship_id = rt.id
            WHERE rt.name = 'inhibits'
        ),
        expr AS (
            SELECT er.id AS expr_id, er.from_entity_id AS prot_id, er.to_entity_id AS org_id, er.confidence AS  expr_conf, er.derivation_depth AS expr_depth, er.derived_from AS expr_from
            FROM entity_relations er
            JOIN relationship_types rt ON er.relationship_id = rt.id
            WHERE rt.name = 'expressed_by'
        ),
        cau AS (
            SELECT er.id AS cau_id, er.from_entity_id AS org_id, er.to_entity_id AS dis_id, er.confidence AS cau_conf, er.derivation_depth AS cau_depth, er.derived_from AS cau_from
            FROM entity_relations er
            JOIN relationship_types rt ON er.relationship_id = rt.id
            WHERE rt.name = 'causes'
        )
        SELECT inh.inh_id, inh.mol_id,            inh.prot_id, expr.expr_id, expr.org_id, cau.cau_id, cau.dis_id, inh.inh_conf, inh.inh_depth, inh.inh_from, expr.expr_conf, expr.expr_depth, expr.expr_from, cau.cau_conf, cau.cau_depth, cau.cau_from
        FROM inh
        JOIN expr ON inh.prot_id = expr.prot_id
        JOIN cau ON expr.org_id = cau.org_id
        WHERE NOT EXISTS (
            SELECT 1 FROM entity_relations existing
            WHERE existing.from_entity_id = inh.mol_id
                AND existing.to_entity_id = cau.dis_id
                AND existing.relationship_id = :treats_id
        )
        """)

    candidates = db.execute(candidate_sql, {"treats_id": treats_id}).mappings().all()

    inserted_count = 0
    skipped_depth = 0
    skipped_cycle = 0
    derived_this_run = set()
    for row in candidates:
        mol_id = row["mol_id"]
        dis_id = row["dis_id"]

        if (mol_id, dis_id) in derived_this_run:
            print(f"skip (already derived this run): {mol_id} -> {dis_id}")
            continue
        premises = [
            {"id": row["inh_id"], "confidence": row["inh_conf"], "depth": row["inh_depth"] or 0},
            {"id": row["expr_id"], "confidence": row["expr_conf"], "depth": row["expr_depth"] or 0},
            {"id": row["cau_id"], "confidence": row["cau_conf"], "depth": row["cau_depth"] or 0}
        ]
        premise_ids = {p["id"] for p in premises}

        derived_meta = weigh_derived_fact(premises)

        if derived_meta["depth"] > MAX_DEPTH:
            print(f"skip (depth {derived_meta['depth']} > MAX_DEPTH): {mol_id} -> {dis_id}")
            skipped_depth += 1
            continue

        if would_create_cycle(db, mol_id, treats_id, dis_id, premise_ids):
            print(f"Skip (cycle detected): {mol_id} -> {dis_id}")
            skipped_cycle += 1
            continue

        db.execute(text("""
            INSERT INTO entity_relations (from_entity_id, to_entity_id, relationship_id, confidence, evidence_count, derived_from, derivation_depth, context)
            VALUES
            (:from_id, :to_id, :rel_id,
            :confidence, 1, :derived_from, :depth, :context)
            """),
        {
            "from_id": mol_id,
            "to_id": dis_id,
            "rel_id": treats_id,
            "confidence": derived_meta["confidence"],
            "derived_from": list(premise_ids),
            "depth": derived_meta["depth"],
            "context": "Derived via inhibits + expressd_by + causes",
        }
        )

        inserted_count += 1
        print(f"Derived treats: {mol_id} -> {dis_id} (tier {derived_meta['confidence']}, depth {derived_meta['depth']})")
        derived_this_run.add((mol_id, dis_id))
    db.commit()
    print(f"causal_path complete --- inserted: {inserted_count}, skipped (depth): {skipped_depth}, skipped (cycle): {skipped_cycle}")

RULES = {
    "causal_path": causal_path,
}
