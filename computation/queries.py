from sqlalchemy import text

# Single‑hop queries
SINGLE_HOP_QUERY = text("""
    SELECT
        e_from.id AS from_id,
        e_from.name AS from_name,
        e_to.id AS to_id,
        e_to.name AS to_name,
        er.id AS relationship_id,
        rt.name AS relationship_type,
        er.confidence,
        er.evidence_count,
        er.context,
        1 AS depth
    FROM entity_relations er
    JOIN entities e_from ON er.from_entity_id = e_from.id
    JOIN entities e_to ON er.to_entity_id = e_to.id
    JOIN relationship_types rt ON er.relationship_id = rt.id
    WHERE e_from.name = :source_name
        AND rt.name = :relationship_type
    """)

# Relationship‑type‑constrained path query for verification mode
# Walks forward from ``source_id`` to ``target_id`` while only allowing
# relationship types listed in ``allowed`` and ensures that the claimed
# ``relationship_type`` appears at least once (tracked by ``claimed_seen``).
# ``max_depth`` caps the recursion depth.
CONSTRAINT_QUERY = text("""
    WITH RECURSIVE traversal AS (
    --- Anchor: first hop from source, allowed types only
    SELECT
        er.from_entity_id,
        er.to_entity_id,
        er.confidence,
        er.evidence_count,
        1 AS depth,
        ARRAY[er.from_entity_id, er.to_entity_id] AS path,
        ARRAY[er.id] AS relationship_ids,
        ARRAY[rt.name] AS rel_names,
        CASE WHEN rt.name = :claimed THEN 1 ELSE 0 END AS claimed_seen
    FROM entity_relations er
    JOIN relationship_types rt ON er.relationship_id = rt.id
    WHERE er.from_entity_id = :source_id
        AND rt.name = ANY(:allowed)

    UNION ALL

    --- Recursive: one more allowed hop; running max confidence/evidence; no cycles
    SELECT
        er.from_entity_id,
        er.to_entity_id,
        GREATEST(t.confidence, er.confidence) AS confidence,
        GREATEST(t.evidence_count, er.evidence_count) AS evidence_count,
        t.depth + 1,
        t.path || er.to_entity_id,
        t.relationship_ids || er.id,
        t.rel_names || rt.name,
        t.claimed_seen + CASE WHEN rt.name = :claimed THEN 1 ELSE 0 END
    FROM entity_relations er
    JOIN relationship_types rt ON er.relationship_id = rt.id
    JOIN traversal t ON er.from_entity_id = t.to_entity_id
    WHERE rt.name = ANY(:allowed)
        AND t.depth < :max_depth
        AND er.to_entity_id != ALL(t.path)
    )
    SELECT
        t.path,
        t.relationship_ids,
        t.rel_names AS relationship_path,
        t.confidence,
        t.evidence_count,
        t.depth
    FROM traversal t
    WHERE t.to_entity_id = :target_id
        AND t.claimed_seen > 0
        AND t.depth <= :max_depth
    """)

SINGLE_HOP_BACKWARD_QUERY = text("""
    SELECT
        e_from.id AS from_id,
        e_from.name AS from_name,
        e_to.id AS to_id,
        e_to.name AS to_name,
        er.id AS relationship_id,
        rt.name AS relationship_type,
        er.confidence,
        er.evidence_count,
        er.context,
        1 AS depth
    FROM entity_relations er
    JOIN entities e_from ON er.from_entity_id = e_from.id
    JOIN entities e_to ON er.to_entity_id = e_to.id
    JOIN relationship_types rt ON er.relationship_id = rt.id
    WHERE e_to.name = :target_name
        AND rt.name = :relationship_type
    """)

TWO_HOP_FORWARD_QUERY = text("""
    WITH RECURSIVE traversal AS (
        SELECT
            er.from_entity_id,
            er.to_entity_id,
            er.relationship_id,
            er.confidence,
            er.evidence_count,
            1 AS depth,
            ARRAY[er.from_entity_id, er.to_entity_id] AS path,
            ARRAY[er.id] AS relationship_ids
        FROM entity_relations er
        JOIN relationship_types rt ON er.relationship_id = rt.id
        JOIN entities e ON er.from_entity_id = e.id
        WHERE e.name = :source_name
            AND rt.name = :first_relationship

        UNION ALL

        SELECT
            er.from_entity_id,
            er.to_entity_id,
            er.relationship_id,
            er.confidence,
            er.evidence_count,
            t.depth + 1,
            t.path || er.to_entity_id,
            t.relationship_ids || er.id
        FROM entity_relations er
        JOIN traversal t ON er.from_entity_id = t.to_entity_id
        JOIN relationship_types rt ON er.relationship_id = rt.id
        WHERE rt.name = :second_relationship
            AND t.depth < :max_depth
            AND er.to_entity_id != ALL(t.path)
    )
    SELECT
        e1.name AS from_name,
        e2.name AS to_name,
        t.from_entity_id AS from_entity_id,
        t.to_entity_id AS to_entity_id,
        t.relationship_ids AS relationship_ids,
        rt.name AS relationship_type,
        t.confidence,
        t.evidence_count,
        t.depth
    FROM traversal t
    JOIN entities e1 ON t.from_entity_id = e1.id
    JOIN entities e2 ON t.to_entity_id = e2.id
    JOIN relationship_types rt ON t.relationship_id = rt.id
    WHERE t.depth = :max_depth
    """)

TWO_HOP_BACKWARD_QUERY = text("""
    WITH RECURSIVE traversal AS (
        SELECT
            er.from_entity_id,
            er.to_entity_id,
            er.relationship_id,
            er.confidence,
            er.evidence_count,
            1 AS depth,
            ARRAY[er.from_entity_id, er.to_entity_id] AS path,
            ARRAY[er.id] AS relationship_ids
        FROM entity_relations er
        JOIN relationship_types rt ON er.relationship_id = rt.id
        JOIN entities e ON er.to_entity_id = e.id
        WHERE e.name = :target_name
            AND rt.name = :first_relationship

        UNION ALL

        SELECT
            er.from_entity_id,
            er.to_entity_id,
            er.relationship_id,
            er.confidence,
            er.evidence_count,
            t.depth + 1,
            t.path || er.from_entity_id,
            t.relationship_ids || er.id
        FROM entity_relations er
        JOIN traversal t ON er.to_entity_id = t.from_entity_id
        JOIN relationship_types rt ON er.relationship_id = rt.id
        WHERE rt.name = :second_relationship
            AND t.depth < :max_depth
            AND er.from_entity_id != ALL(t.path)
    )
    SELECT
        e1.name AS from_name,
        e2.name AS to_name,
        t.from_entity_id AS from_entity_id,
        t.to_entity_id AS to_entity_id,
        t.relationship_ids AS relationship_ids,
        rt.name AS relationship_type,
        t.confidence,
        t.evidence_count,
        t.depth
    FROM traversal t
    JOIN entities e1 ON t.from_entity_id = e1.id
    JOIN entities e2 ON t.to_entity_id = e2.id
    JOIN relationship_types rt ON t.relationship_id = rt.id
    WHERE t.depth = :max_depth
    """)

NEIGHBORHOOD_QUERY = text("""
    WITH RECURSIVE neighborhood AS (
        -- ANCHOR: every edge touching the start entity, one row PER EDGE.
        SELECT
            er.from_entity_id,
            er.to_entity_id,
            CASE WHEN er.from_entity_id = :entity_id
                THEN er.to_entity_id
                ELSE er.from_entity_id
            END AS connected_id,
            ARRAY[er.id] AS relationship_ids,
            rt.name AS relationship_type,
            CASE WHEN er.from_entity_id = :entity_id
                THEN 'outgoing'
                ELSE 'incoming'
            END AS direction,
            er.confidence,
            er.evidence_count,
            ARRAY[
                CASE WHEN er.from_entity_id = :entity_id
                    THEN er.from_entity_id
                    ELSE er.to_entity_id
                END,
                CASE WHEN er.from_entity_id = :entity_id
                    THEN er.to_entity_id
                    ELSE er.from_entity_id
                END
            ] AS path,
            1 AS depth
        FROM entity_relations er
        JOIN relationship_types rt ON er.relationship_id = rt.id
        WHERE er.from_entity_id = :entity_id
            OR er.to_entity_id = :entity_id

        UNION ALL

        SELECT
            er.from_entity_id,
            er.to_entity_id,
            CASE WHEN er.from_entity_id = n.connected_id
                THEN er.to_entity_id
                ELSE er.from_entity_id
            END AS connected_id,
            n.relationship_ids || er.id AS relationship_ids,
            rt.name AS relationship_type,
            CASE WHEN er.from_entity_id = n.connected_id
                THEN 'outgoing'
                ELSE 'incoming'
            END AS direction,
            er.confidence,
            er.evidence_count,
            n.path || CASE WHEN er.from_entity_id = n.connected_id
                        THEN er.to_entity_id
                        ELSE er.from_entity_id
                    END AS path,
            n.depth + 1 AS depth
        FROM entity_relations er
        JOIN neighborhood n ON (
            er.from_entity_id = n.connected_id
            OR er.to_entity_id = n.connected_id
        )
        JOIN relationship_types rt ON er.relationship_id = rt.id
        WHERE n.depth < :max_depth
            AND CASE WHEN er.from_entity_id = n.connected_id
                    THEN er.to_entity_id
                    ELSE er.from_entity_id
                END != ALL(n.path)
    )
    SELECT
        e.name AS entity_name,
        n.connected_id AS connected_entity_id,
        n.from_entity_id,
        n.to_entity_id,
        n.relationship_ids AS relationship_ids,
        n.relationship_type,
        n.direction,
        n.confidence,
        n.evidence_count,
        n.depth
    FROM neighborhood n
    JOIN entities e ON n.connected_id = e.id
    ORDER BY n.depth, e.name, n.relationship_ids
    LIMIT :row_limit
    """)

PATH_QUERY = text("""
    WITH RECURSIVE path_search AS (
        SELECT
            er.from_entity_id,
            er.to_entity_id,
            ARRAY[er.relationship_id] AS relationship_ids,
            1 AS depth,
            ARRAY[er.from_entity_id] AS visited,
            ARRAY[rt.name] AS relationship_path
        FROM entity_relations er
        JOIN relationship_types rt ON er.relationship_id = rt.id
        WHERE er.from_entity_id = :start_entity_id

        UNION ALL
        SELECT
            er.from_entity_id,
            er.to_entity_id,
            ps.relationship_ids || er.relationship_id AS relationship_ids,
            ps.depth + 1,
            ps.visited || er.to_entity_id,
            ps.relationship_path || rt.name
        FROM entity_relations er
        JOIN path_search ps ON er.from_entity_id = ps.to_entity_id
        JOIN relationship_types rt ON er.relationship_id = rt.id
        WHERE ps.depth < :max_depth
            AND er.to_entity_id != ALL(ps.visited)
            AND ps.to_entity_id != :end_entity_id
    )
    SELECT
        e1.name AS from_name,
        e2.name AS to_name,
        ps.relationship_ids AS relationship_ids,
        ps.relationship_path,
        ps.depth
    FROM path_search ps
    JOIN entities e1 ON ps.from_entity_id = e1.id
    JOIN entities e2 ON ps.to_entity_id = e2.id
    WHERE ps.to_entity_id = :end_entity_id
    ORDER BY ps.depth
    LIMIT 1
    """)
