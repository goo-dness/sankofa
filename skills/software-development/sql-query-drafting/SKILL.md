---
name: sql-query-drafting
description: Draft concise PostgreSQL queries, ending with a semicolon.
version: 0.1.0
author: Goodness Akuba, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [sql, query, postgresql]
    related_skills: [codebase-inspection]
---

# SQL Query Drafting Skill

## When to Use
- Need raw PostgreSQL queries for counts, joins, diagnostics, or quick data checks.

## Prerequisites
- Access to the PostgreSQL database via the `DATABASE_URL` environment variable.
- `psql` or any SQL client that can execute statements.

## How to Run
```sql
-- Example: count entities
SELECT COUNT(*) AS entity_count FROM entities;
```
Each statement must end with a semicolon (`;`). Separate multiple statements with a blank line.

## Quick Reference
- Count rows: `SELECT COUNT(*) FROM <table>;`
- Simple join: `SELECT e.id, rt.name FROM entity_relations er JOIN relationship_types rt ON er.relationship_id = rt.id LIMIT 10;`

## Pitfalls
- Missing terminating semicolon causes a syntax error.
- Do not embed explanatory text inside the SQL block.
- Add `LIMIT` for large result sets to avoid overwhelming output.

## Verification
Run the query; successful execution returns rows without error.

## Reference
- `references/cheat-sheet.md`
