# PostgreSQL backend (optional)

Show Type runs on **SQLite by default** — zero dependencies, nothing to set up.
When the `DATABASE_URL` environment variable is set, the same code talks to **PostgreSQL**
instead (via [psycopg](https://www.psycopg.org/) v3, imported lazily only on that path).
The schema — `axis` / `show` / `show_genre` / `score`, with identical column names,
uniqueness constraints, checks, and foreign keys — is the same on both backends.

## 1. Install the optional dependency

```bash
pip install -e '.[postgres]'      # installs psycopg[binary] alongside the base deps
```

The base install (`pip install -e .`) never pulls in psycopg; it's only needed for Postgres.

## 2. Start a Postgres instance

Any Postgres 14+ works. A throwaway one via Docker:

```bash
docker run -d --rm --name ti-pg \
  -e POSTGRES_PASSWORD=pw -e POSTGRES_DB=taste \
  -p 5432:5432 postgres:16
```

## 3. Point the app at it and load the data

```bash
export DATABASE_URL='postgresql://postgres:pw@127.0.0.1:5432/taste'

# One command: init schema + seed the 8 axes + backfill catalog + genres + quality,
# all from the committed CSVs in docs/.
python -m showtype db-load
```

`db-load` is equivalent to running these individually (each honours `DATABASE_URL`):

```bash
python -m showtype init-db
python -m showtype backfill --csv docs/catalog-scores.csv
python -m showtype tag-genres
python -m showtype load-quality
```

After loading, every read/query command works against Postgres transparently:

```bash
python -m showtype similar "The Wire" -n 5
python -m showtype query --where "sweep>=8" --where "register<=4"
python -m showtype serve               # web UI, backed by Postgres
```

To go back to SQLite, just `unset DATABASE_URL` (the `--db` path is used again).

## Notes

- **The offline build stays SQLite/zero-dependency.** `python scripts/build_static.py`
  always produces `docs/showtype.html` from SQLite, even if `DATABASE_URL` is set —
  it forces the SQLite backend so the self-contained page never depends on psycopg or a
  running database.
- **Schema parity.** SQLite uses `showtype/schema.sql`; Postgres uses
  `showtype/schema_pg.sql` (same tables/columns/constraints, with
  `GENERATED ALWAYS AS IDENTITY` PKs and `TIMESTAMP DEFAULT now()` timestamps). Both are
  idempotent (`CREATE TABLE IF NOT EXISTS` + an additive column migration).

## Running the parity tests

`tests/test_backends.py` builds a SQLite DB from the committed CSVs and checks basic
invariants. If `DATABASE_URL` is set **and** psycopg is importable, it also builds Postgres
from the same CSVs and asserts the two backends agree (counts, axes, vectors, genres,
quality, `nearest`, `recommend`). Otherwise the Postgres cases skip gracefully.

```bash
pip install pytest
export DATABASE_URL='postgresql://postgres:pw@127.0.0.1:5432/taste'   # optional
pytest -q
```
