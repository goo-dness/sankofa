from sqlalchemy import text

SINGLE_HOP_QUERY = text("""
    SELECT
        e_from.id AS from_id,
        e_from.name AS from_name,
        e_to.id AS to_id,
        e_to.name AS to_name,
        rt.name AS relationship_type,
        er.confidence,
        er.evidence_count,
        er.context
    FROM entity_relations er
    JOIN entities e_from ON er.from_entity_id = e_from.id
    JOIN entities e_to ON er.to_entity_id = e_to.id
    JOIN relationship_types rt ON er.relarionship_id = rt.id
    WHERE e_from.name = :source_name
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
            ARRAY[er.from_entity_id, er.to_entity_id] AS path
        FROM entity_relations er
        JOIN relationship_typea rt ON er.relationship_id = rt.id
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
            t.path || er.to_entity_id
    )
    """)
