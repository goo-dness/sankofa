from sqlalchemy import text

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
        -- (The old version used DISTINCT ON, which kept one arbitrary edge per
        -- neighbor and silently deleted the rest.)
        SELECT
            er.from_entity_id,
            er.to_entity_id,
            -- the entity on the other end of this edge from the start entity
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
            -- path = every entity visited so far: the start entity, then this neighbor.
            -- Including the neighbor stops a self-loop from re-walking itself.
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

        -- UNION ALL, not UNION: UNION would deduplicate identical rows and can
        -- hide legitimate parallel edges between the same two entities.
        UNION ALL

        -- RECURSIVE STEP: walk one more edge out from each neighbor found so far.
        -- Note: "direction" here is relative to n.connected_id, not the start entity.
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
            -- cycle guard: never step onto an entity already on this path
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
    -- Nearest neighbors first, so a truncated result keeps the closest facts.
    -- The final key makes the order deterministic (the old one wasn't).
    ORDER BY n.depth, e.name, n.relationship_ids
    -- Hard row cap, passed in from the executor.
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
