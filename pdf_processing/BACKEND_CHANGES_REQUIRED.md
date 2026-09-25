# Backend Changes Required for Reliable Import Protection

**Document status:** Informational — for the backend team.  
**Scope:** `pdf_processing` module only. No backend code was modified.

---

## Why This Document Exists

The current `POST /marks/import` endpoint processes records one at a time and
commits each record in a separate SQLite transaction.  
This design means:

- A **mid-flight network timeout** leaves the database in a **partially saved state**.
- The PDF processing module cannot know how many records were committed before
  the connection dropped.
- Automatic retry after a timeout risks **double-saving** records.

The `TeacherImportWorkflow` handles this conservatively:

- Any timeout or connection loss during an **actual import** sets the workflow
  to `STATUS_UNCERTAIN`.
- The teacher must call `acknowledge_uncertain_import()` and manually verify
  the database before re-submitting.

The following backend changes would remove this limitation.

---

## Recommended Backend Changes

### 1. Wrap the import loop in a single transaction (highest priority)

**File:** `backend/services/marks_import_service.py`

**Current behaviour:** Each record's `INSERT`/`UPDATE` is committed
immediately inside the loop.

**Requested behaviour:** Open one transaction before the loop and commit it
once after all records have been processed.  If any record fails a
validation rule, roll back the entire batch.

```python
# Pseudocode
conn = get_connection()
try:
    conn.execute("BEGIN")
    for record in imported_records:
        # ... validate and upsert ...
    if not dry_run:
        conn.commit()
    else:
        conn.rollback()
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
```

**Why this matters:** A timeout during a transactional import means either
**all** records were saved or **none** were — the teacher can safely retry.

---

### 2. Add a unique constraint on the marks table (medium priority)

**File:** `backend/database/database.py`

**Current schema (marks table):**

```sql
CREATE TABLE IF NOT EXISTS marks (
    mark_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL,
    subject_id  INTEGER NOT NULL,
    exam_id     INTEGER NOT NULL,
    marks_obtained REAL NOT NULL,
    max_marks   REAL NOT NULL,
    ...
);
```

There is no `UNIQUE` constraint on `(student_id, subject_id, exam_id)`.
The backend performs a manual `SELECT` then `INSERT`/`UPDATE`, which works
but is not race-safe and does not enforce idempotency at the DB level.

**Requested change:**

```sql
CREATE TABLE IF NOT EXISTS marks (
    mark_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  INTEGER NOT NULL,
    subject_id  INTEGER NOT NULL,
    exam_id     INTEGER NOT NULL,
    marks_obtained REAL NOT NULL,
    max_marks   REAL NOT NULL,
    UNIQUE (student_id, subject_id, exam_id),  -- <-- add this
    ...
);
```

And update the upsert to use `INSERT OR REPLACE` or `ON CONFLICT DO UPDATE`
instead of the manual SELECT.

**Migration:** Existing databases will need `ALTER TABLE` or a migration script.

---

### 3. Add an idempotency key (optional / long-term)

If the backend wants to support **safe retry after timeout** without requiring
a unique DB constraint, it can accept an `X-Idempotency-Key` header:

```
POST /marks/import
X-Idempotency-Key: <uuid>
```

- The backend stores the key and the result of the first request.
- On a retry with the same key, it returns the cached result immediately
  without re-processing.

**This is not implemented in the current PDF processing module** because the
backend does not yet support it.  Adding it would allow the workflow to retry
safely after a timeout.

---

## Current Workaround (already implemented)

| Scenario | Workflow behaviour |
|---|---|
| Dry-run timeout | `dry_run_passed=False`; safe to retry dry-run immediately |
| Dry-run connection error | `dry_run_passed=False`; safe to retry |
| Actual import timeout | `import_status=UNCERTAIN`; retry **blocked** |
| Actual import connection error | `import_status=UNCERTAIN`; retry **blocked** |
| Actual import HTTP 4xx | `import_status=FAILED`; safe to retry after correcting data |
| Actual import HTTP 200 (partial) | `import_status=SUCCESS`; all failures are reported in `error_reasons` |
| Duplicate submission (SUCCESS state) | `DuplicateImportError` raised; no network call made |
| UNCERTAIN not acknowledged | `UncertainImportError` raised; no network call made |

The teacher can clear an `UNCERTAIN` lock by calling
`workflow.acknowledge_uncertain_import(acknowledged_by=..., notes=...)`.
This resets the workflow to `FAILED` and clears the dry-run, requiring
a fresh dry-run before re-import.
