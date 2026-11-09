# PROJECT_RULES.md — Hishabi

<?chip date 2026-11-09?> · <?chip mention 118321964913492586446 Zahid Hasan?>

## Team and File Ownership

Two members share this repository. Each file has exactly one owner. The owner is the only person allowed to create or edit that file.

| Path | Owner | Never touched by |
| --- | --- | --- |
| `app/core/config.py` | Zahid | Azaz |
| `app/core/database.py` | Zahid | Azaz |
| `app/core/security.py` | Zahid | Azaz |
| `app/models/` | Zahid | Azaz |
| `app/services/audit_service.py` | Zahid | Azaz |
| `app/api/deps.py` | Zahid | Azaz |
| `app/api/v1/stock.py` | Zahid | Azaz |
| `app/api/v1/sales.py` | Zahid | Azaz |
| `app/api/v1/payments.py` | Zahid | Azaz |
| `app/api/v1/ai.py` | Zahid | Azaz |
| `app/api/v1/auth.py` | Azaz | Zahid |
| `app/api/v1/users.py` | Azaz | Zahid |
| `app/api/v1/products.py` | Azaz | Zahid |
| `app/api/v1/categories.py` | Azaz | Zahid |
| `app/schemas/auth.py`, `user.py` | Azaz | Zahid |
| `app/schemas/product.py`, `category.py` | Azaz | Zahid |
| `frontend/src/api/client.js` | Zahid | Azaz |
| `frontend/src/pages/` | Split per page | Each member owns their own pages only |

> [!NOTE]
> If you need to change a file you do not own, say so in the pull request description and wait for approval. Never edit it silently.

> [!NOTE]
> A pull request that touches a shared file must include the line `Shared file touched: Yes - <path>` in its description.

## Folder Structure

Every file must live in one of these places. Do not create a new top-level folder.

```text
hishabi/
├── app/
│   ├── core/           # config, database, security (Zahid)
│   ├── models/         # SQLAlchemy models (Zahid)
│   ├── schemas/        # Pydantic request and response schemas
│   ├── services/       # business logic and shared helpers
│   ├── api/
│   │   ├── deps.py     # get_current_user, require_roles (Zahid)
│   │   └── v1/         # one file per resource
│   ├── db/             # scripts for seeding and initialising
│   └── main.py         # FastAPI app entry point
├── alembic/            # migrations
├── tests/
│   ├── unit/
│   └── integration/
├── docs/               # schema.md, api-contract.md, diagrams
├── scripts/            # shell helper scripts
├── frontend/           # React app (Vite)
├── .env.example        # committed template
├── requirements.txt
└── PROJECT_RULES.md
```

Rules:

- One resource per file in `app/api/v1/`. The file name matches the resource.
- One model per file in `app/models/`. The file name is the snake_case of the model.
- Never put SQL queries inside an endpoint file. Move them into `app/services/`.
- Never write to a file on the server's disk. Generate reports in memory and stream them.

## Naming Conventions

| Thing | Rule | Example |
| --- | --- | --- |
| Python file | snake_case | `stock_movement.py` |
| Model class | PascalCase, singular | `StockMovement` |
| Pydantic schema | PascalCase with a suffix | `StockMovementCreate`, `StockMovementOut` |
| API path | plural noun, kebab-case | `/api/v1/stock-movements` |
| Database table | snake_case, plural | `stock_movements` |
| Database column | snake_case | `low_stock_threshold` |
| React component | PascalCase | `ProductList.jsx` |
| Branch | `branch_<name>` | `branch_zahid`, `branch_azaz` |

Endpoint rules:

- Every path starts with `/api/v1/`.
- Use HTTP verbs for the action: `GET` reads, `POST` creates, `PUT` replaces, `PATCH` updates, `DELETE` removes.
- A plural path with an integer id is one resource: `GET /api/v1/products/12`.
- Name the router variable `router`, not `app`, in every file in `app/api/v1/`.

## API Response and Error Format

Every endpoint in the project returns the same JSON shape. Do not invent a new shape.

A successful single resource returns the resource object directly.

```json
{
  "id": 1,
  "name": "চাল",
  "unit": "kg",
  "sale_price": "60.00",
  "current_stock": "50.000"
}
```

A successful list returns a list under a named key.

```json
{
  "items": [
    { "id": 1, "name": "চাল" }
  ],
  "total": 1
}
```

An error always returns this shape.

```json
{
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "Only 2 kg of চাল is in stock."
  }
}
```

Rules:

- Use the error shape for every failure, including validation errors.
- The `code` is uppercase with underscores, for example `NOT_FOUND`, `FORBIDDEN`, `INVALID_AMOUNT`.
- The `message` is written in plain English and may include a Bangla product or customer name.
- Use the HTTP status code for the status, and the JSON body for the detail. Never return a bare string.

> [!NOTE]
> Money values are strings in JSON so that no rounding is lost. `Decimal` is used on the server.

Define the error model once in `app/schemas/common.py` and import it everywhere.

## Git Workflow Rules

Branches:

| Branch | Purpose |
| --- | --- |
| `main` | Production. Protected. Receives code only from `test`. |
| `test` | Integration. Protected. Every feature lands here first. |
| `branch_zahid` | Zahid's working branch. |
| `branch_azaz` | Azaz's working branch. |

The one rule that matters most:

> The base branch of every pull request is `test`, never `main`.

Daily flow:

1. Start the day on your own branch and pull the latest.
2. Write the feature and its Pytest tests.
3. Commit, then push your own branch.
4. Open a pull request with base `test` and compare your branch.
5. The other member reviews, requests changes if needed, then approves.
6. After both members' work is merged into `test`, run the full test suite.
7. Once the week is stable, open a pull request from `test` to `main`.

```bash
git checkout branch_zahid
git pull origin branch_zahid
git add .
git commit -m "feat: add stock movement endpoint"
git push origin branch_zahid
```

Merge order when both members have open pull requests: merge one first, then have the other pull `test` again before merging.

Commit message format:

```text
feat: add stock movement endpoint
fix: correct balance_after on return
chore: add pytest fixture
docs: update api contract
```

On a merge conflict:

```bash
git fetch origin
git merge origin/test
```

Then open the conflicting files in VS Code, pick the correct version for each, and commit again.

> [!NOTE]
> Never force push to `main` or `test`. They are protected.

## Rules for AI Coding Tools

Paste this at the start of every session with an AI coding tool.

```text
You are working on Hishabi, a FastAPI + React + PostgreSQL capstone project.

Before writing any code:
1. Read PROJECT_RULES.md, docs/schema.md and docs/api-contract.md.
2. Read the task section in the module file for your member.

Hard rules that prevent merge conflicts:
- Do not create or edit any file listed as owned by the other member.
- Do not rename tables, columns or API fields. Use the exact names in docs/schema.md.
- Do not create a new top-level folder or a new shared helper.
- Prefer creating a new file over editing an existing shared file.
- Use the exact request and response JSON format from docs/api-contract.md.
- Read every secret from an environment variable. Never hardcode a key or a password.
- Use Decimal or Numeric for money and quantity. Never use float.
- Write a Pytest test for every feature you add.

Before you write code, list every file you will create or change, and wait for my confirmation.

For each file you create, explain in one sentence what it does and what breaks if it is wrong.
```

> [!NOTE]
> A file that the AI tool cannot explain in one sentence does not belong in the repository.

## Database and Code Rules

Database rules:

- The table and column names in `docs/schema.md` are the source of truth. Never rename them.
- Money and quantity use `Numeric`, which maps to Python `Decimal`. Never use `float`.
- Timestamps use `server_default=func.now()`.
- Primary keys are `Integer` with auto increment.
- Delete is soft. Set `is_active` to false instead of removing a row that other tables reference.
- Use the ORM for every query. Never build SQL strings by hand.
- Every schema change needs an Alembic migration, generated with `alembic revision --autogenerate`.

Secrets and configuration:

- Every setting comes from an environment variable read in `app/core/config.py`.
- `.env` stays on the machine and is never committed. `.env.example` is the committed template.
- The frontend only ever receives `VITE_API_URL`. A `VITE_` variable is visible in the browser, so no secret may use that prefix.
- The AI provider key stays on the server and is never sent to the browser.

Testing rules:

- Every feature has a Pytest test in `tests/unit/`.
- Tests that touch the database use the `hishabi_test` database, never the development one.
- Run the suite with `python -m pytest -q` before opening a pull request.
- Fix the code, not the test. Changing a test expectation to make it pass is not allowed.

Transactions:

- A sale that changes stock, writes a movement row and updates a due runs inside one database transaction.
- Lock the product row before changing stock, then check that the new quantity never goes below zero.
- If any step fails, roll back everything.

Audit logging:

- `audit_service.log_action` is the only way to write an audit row.
- Every critical action calls it: product create, update and delete, stock movement, sale, payment, purchase, and role change.
- The helper signature stays stable because all three modules call it.
