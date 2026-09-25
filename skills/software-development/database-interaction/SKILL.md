# SKILL.md

Use when accessing a PostgreSQL database in the Sankofa project.

## Trigger
When Python code needs to connect to the project's PostgreSQL DB (via SQLAlchemy, psycopg2, etc.), the agent must ensure the `DATABASE_URL` environment variable is present and valid.

## Steps
1. Read the env var: `os.getenv('DATABASE_URL')`.
2. If missing or empty, prompt the user for the full connection string (show example from `.env.example`).
3. Validate the URL format (basic regex) and attempt `create_engine(url)` inside a try/except.
4. On `sqlalchemy.exc.ArgumentError` or connection failure, surface a clear error and ask for correction.
5. After successful validation, create a session (`SessionLocal()`) and close it when done.

## Pitfalls
- Assuming the variable exists leads to `ArgumentError` (as seen in this session).
- Including stray whitespace or newline in the URL breaks the engine.
- Forgetting to close the session leaks connections.
- Using the raw URL without stripping leads to hidden characters.

## References
- `references/connection_handling.md`
