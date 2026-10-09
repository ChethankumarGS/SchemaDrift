# SchemaDrift

SchemaDrift compares two versions of a database schema and tells you what changed and which changes will break running code. Paste the old and new schema, get a colour-coded report: **BREAKING**, **REVIEW** or **SAFE**.

**Live demo:** https://schema-drift-nine.vercel.app/ (an example pair is preloaded, just press *Compare schemas*)

## Why it matters

Most outages from database migrations are avoidable. A dropped column, a new `NOT NULL` without a default, or a narrowed type looks harmless in a pull request and fails in production. SchemaDrift catches these before they ship:

- Review a migration pull request in seconds instead of reading DDL line by line.
- Run it as a check in CI to stop a breaking schema change from merging unnoticed.
- Explain to teammates exactly why a change is risky.

## What it detects

| Level | Examples |
|---|---|
| BREAKING | table or column dropped, `NOT NULL` column added without a default, `NULL` to `NOT NULL`, type narrowed or incompatible (`BIGINT` to `INT`, `VARCHAR(100)` to `VARCHAR(50)`, `TEXT` to `INT`), primary key changed, unique index added or removed |
| REVIEW | default removed or changed, index removed, foreign key added or removed |
| SAFE | table or nullable column added, integer or varchar widened, plain index added, `NOT NULL` relaxed to `NULL` |

A dropped column plus an added column of the same type is flagged as a possible rename. A rename is still breaking for code that uses the old name.

## How to use

1. Open the app. An example pair is already loaded.
2. Paste your current schema on the left and the proposed schema on the right. Both **SQL DDL** (`CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE ... ADD`) and **JSON** are accepted.
3. Press **Compare schemas**. Read the verdict at the top, then each change with its reason.

JSON format:

```json
{
  "tables": {
    "users": {
      "columns": {
        "id": {"type": "bigint", "nullable": false},
        "email": {"type": "varchar(100)", "nullable": false, "default": null}
      },
      "primary_key": ["id"],
      "indexes": {"uq_email": {"columns": ["email"], "unique": true}},
      "foreign_keys": []
    }
  }
}
```

Use it from Python:

```python
from schemadrift import load_schema, diff_schemas, summarize

changes = diff_schemas(load_schema(old_sql), load_schema(new_sql))
print(summarize(changes)["verdict"])   # BREAKING / REVIEW / SAFE / NO CHANGES
```

## Example result

For the built-in example (a proposed `v2` of a users and orders schema) SchemaDrift reports **6 breaking, 2 review, 7 safe**, including:

- BREAKING: table `legacy_audit` was dropped
- BREAKING: `users.tenant_id` is `NOT NULL` with no default
- BREAKING: `orders.total` narrowed from `decimal(10,2)` to `decimal(8,2)`
- BREAKING: unique constraint added on `users(email)`
- REVIEW: `orders.status` lost its default
- SAFE: `users.email` widened from `varchar(100)` to `varchar(255)`

## Run it locally

You need Python 3.10 or newer. No environment variables or secrets are required. The only optional setting is the port.

```bash
git clone https://github.com/ChethankumarGS/SchemaDrift.git
cd SchemaDrift
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python app.py            # http://localhost:5000
```

Optional: `PORT=8000 python app.py` to change the port.

Run the tests:

```bash
python -m pytest -q
```

## Project layout

```
app.py                 Flask app (/ and /healthz)
schemadrift/parser.py  SQL DDL and JSON to a common schema model
schemadrift/diff.py    diff engine and breaking / review / safe rules
schemadrift/examples.py  built-in demo schemas
templates/index.html   report UI
tests/                 parser and diff tests
render.yaml            optional Render blueprint
```

## Deploy

The app is deployed on Vercel with zero configuration (Flask preset). It also runs on Render's free plan using the included `render.yaml` (`gunicorn app:app`).

## Limits

SchemaDrift reads common DDL (`CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE ... ADD`). Views, triggers, stored procedures, check constraints and engine-specific options are ignored. Renames cannot be detected with certainty.

## Author

Chethan Kumar - [GitHub](https://github.com/ChethankumarGS)
