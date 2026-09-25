# SQL Query Cheat Sheet

- Count rows: `SELECT COUNT(*) FROM <table>;`
- Join with alias:
  ```sql
  SELECT e.name, rt.name FROM entities e
  JOIN entity_relations er ON e.id = er.from_entity_id
  JOIN relationship_types rt ON er.relationship_id = rt.id;
  ```
- Add limit:
  ```sql
  SELECT * FROM <table> LIMIT 20;
  ```
- Always terminate with a semicolon.
