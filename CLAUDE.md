# Working on geoapps

Read `docs/design/01-design-plan.md` before changing behaviour; the workstream letters (A–M) and gate ids (E4, H1, ...) used in code and tests come from it. `docs/design/03-data-model.md` is the reference for tables.

Rules the code relies on:

- `geoapps-db` is the only package that writes to Postgres. API routes and worker steps call `geoapps_db.repo`; they never build their own queries. Models and repo functions live in one module per schema and are re-exported from `geoapps_db.models` and `geoapps_db.repo`.
- Facts that change over time carry `valid tstzrange`; a change closes the old range and opens a new row. Never edit a shipped migration; add one.
- Imported data records its `core.dataset` (URL, licence, checksum) and an xref per provider record id.
- `geoapps-core` has no I/O: no database, no HTTP, no files. Science and rules go there so they can be tested without Postgres.
- Every detection is born `predicted`. Only `repo.record_verdict` changes its status, and only a validated detection raises alerts or goes downstream (gate E4).
- Kinds plug in through `geoapps_core.kinds.register_kind`; core code never branches on a kind's name.
- ETL steps are registered with `@etl(name=..., params=SomePydanticModel)`. Parameters are validated before a job exists (H1), and a failed step rolls back everything it wrote.
- Shape and equation comments sit to the right of array code, e.g. `# (D,) → (D,)`.
- No conflict or other sensitive event kinds.

Checks before committing:

```bash
uv run ruff check packages && uv run ruff format --check packages
GEOAPPS_TEST_DATABASE_URL=... uv run pytest
cd web && npm run build
```

After changing an API schema, regenerate the client types: `uv run geoapps-openapi web/openapi.json && (cd web && npm run gen:api)`.
