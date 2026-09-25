# StudentInsight

> **Student Performance Analytics & Automated Marksheet Processing Platform**

StudentInsight is an institutional academic performance analytics system that automates the ingestion, validation, and analytics of student examination records. 

This repository houses the core platform components, featuring the **PDF Processing & Data Validation Module (Member 2)**, which provides an audited, safe ingestion gateway converting raw institutional marksheets into normalized database records.

---

## Architecture Overview

```
                                 PDF PROCESSING & INGESTION PIPELINE
 ┌──────────────────────┐
 │ Marksheet PDF Upload │ (Sample: 52 Students, 5 Subjects)
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │   extractor.py       │  Extracts structured text streams via pdfplumber
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │     parser.py        │  Extracts Exam Metadata, Subjects & Student Rows
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │    cleaner.py &      │  Normalizes Roll Numbers & Names; validates marks,
 │    validator.py      │  bounds (0 <= marks <= max), duplicates & ABS
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │    normalizer.py     │  Produces Canonical Internal Structure A Document
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │      review.py       │  Teacher Review Session: Editable working draft,
 │(TeacherReviewSession)│  isolated from original data, gates confirmation
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │      mapper.py       │  Pivots wide rows to Structure B (260 relational records)
 └──────────┬───────────┘
            │
            ▼
 ┌──────────────────────┐
 │  backend_client.py & │  Two-Phase Safe Import:
 │  import_workflow.py  │  Phase 1: POST /marks/import?dry_run=true
 └──────────┬───────────┘  Phase 2: POST /marks/import?dry_run=false (Explicit Confirm)
            │
            ▼
 ┌──────────────────────┐
 │  FastAPI & SQLite DB │  Upserts marks, tracks student analytics & metrics
 └──────────────────────┘
```

---

## PDF Processing Module (Member 2)

The `pdf_processing` module is responsible for parsing institutional examination marksheets (e.g., college semester exams, midterms, unit tests), validating scores, and enabling safe teacher verification before persisting records to the database.

### Key Capabilities

1. **Automated Header & Metadata Extraction**: Automatically parses institution name, course (`B.TECH`), semester (`II`), branch (`AIML`), exam name (`MST-2`), and exam session (`JULY 2026`) without hardcoding.
2. **Robust Multi-Page Student Parsing**: Reliably parses multi-page marksheets (e.g., Page 1 header + student rows, Page 2 continuing student rows without repeating headers), supporting variable-length Indian student names (1 to 5 words).
3. **Strict Absentee (`"ABS"`) Preservation**: Absent student scores are strictly preserved as the literal string `"ABS"` throughout all pipeline stages, never coerced to 0 or `None`.
4. **Isolated Teacher Review Session**: Creates a working copy of extracted data for inline teacher adjustments while preserving an immutable snapshot of original extracted records for institutional auditability.
5. **Two-Stage Import Gatekeeper**:
   - **Dry-Run Validation**: Submits payload to backend with `dry_run=true` to test validation rules without writing to the database.
   - **Explicit Secondary Confirmation**: Requires explicit teacher authorization (`import_confirmation=True`) before executing live database writes (`dry_run=false`).
6. **Duplicate & Failure Protection**:
   - Blocks accidental double-submissions with `DuplicateImportError` (0 network calls).
   - Detects mid-flight network timeouts, transitioning to `STATUS_UNCERTAIN` to prevent automatic retries that could corrupt data, requiring manual audit and explicit acknowledgement (`acknowledge_uncertain_import`).
7. **Streamlit Frontend Integration**: Features a stateless adapter (`workflow_adapter.py`) that wires the end-to-end pipeline directly into Tab 3 of the Teacher Dashboard (`pdf_upload_tab.py`).

---

## Project Structure

```
StudentInsight/
├── pdf_processing/                   # Member 2: PDF Processing & Validation
│   ├── __init__.py                   # Package exports
│   ├── extractor.py                  # Low-level PDF text stream extraction
│   ├── parser.py                     # Header, metadata, and student row parsing
│   ├── cleaner.py                    # Whitespace cleaning and uppercase normalization
│   ├── validator.py                  # Student record and score validation
│   ├── normalizer.py                 # Canonical Structure A generator
│   ├── processor.py                  # End-to-end extraction pipeline entrypoint
│   ├── review.py                     # TeacherReviewSession data review & gating
│   ├── mapper.py                     # Wide-to-relational Structure B payload mapper
│   ├── backend_client.py             # HTTP client for POST /marks/import API
│   ├── import_workflow.py            # Two-stage gated import orchestrator
│   ├── workflow_adapter.py           # Stateless adapter for Streamlit UI
│   ├── PDF_INPUT_SPECIFICATION.md    # 500+ line detailed data specification
│   ├── BACKEND_CHANGES_REQUIRED.md   # Backend transaction & constraint recommendations
│   └── samples/
│       └── sample_marks.pdf          # 2-page sample marksheet (52 students, 5 subjects)
├── app/
│   └── frontend/
│       └── dashboards/
│           ├── pdf_upload_tab.py     # Streamlit Tab 3 UI component for PDF import
│           └── teacher_dashboard.py  # Teacher dashboard incorporating PDF import tab
├── tests/                            # Comprehensive Test Suites (10 test modules)
│   ├── test_extractor.py             # PDF text extraction tests
│   ├── test_parser.py                # Regex and student row parsing tests
│   ├── test_normalizer.py            # Structure A normalization rules tests
│   ├── test_review.py                # Teacher review draft isolation & gating tests
│   ├── test_end_to_end.py            # PDF to Structure B transformation tests
│   ├── test_backend_client.py        # Backend HTTP client & error handling tests
│   ├── test_import_workflow.py       # Import workflow, duplicate & timeout tests
│   ├── test_workflow_adapter.py      # Streamlit workflow adapter tests
│   ├── test_pdf_upload_tab.py        # Streamlit UI tab lifecycle tests
│   └── test_e2e_backend_integration.py # Full PDF-to-SQLite database verification tests
├── sample_data/
│   └── college_marks.pdf             # Reference marksheet PDF
├── README.md                         # Project documentation
└── .gitignore                        # Git ignore rules
```

---

## Setup and Installation

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.11, 3.12, 3.14)
- Git

### 2. Environment Setup
```bash
# Clone the repository
git clone https://github.com/BobtheBuilder-193/student-insight.ai.git
cd student-insight.ai

# Switch to the PDF processing feature branch
git checkout feature/pdf-processing

# Create and activate virtual environment
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate

# Install PDF processing dependencies
pip install pdfplumber
```

---

## Usage Guide

### Running the Complete PDF Pipeline Programmatically

```python
from pdf_processing.processor import process_pdf
from pdf_processing.review import create_review_session
from pdf_processing.import_workflow import TeacherImportWorkflow

# 1. Extract and normalize PDF data
result = process_pdf("pdf_processing/samples/sample_marks.pdf")

# 2. Initialize teacher review session
session = create_review_session(result)

# 3. Confirm review draft
session.confirm(confirmed_by="Prof. Sharma", academic_year="2025-2026")

# 4. Initialize import workflow
workflow = TeacherImportWorkflow(session)

# 5. Run dry-run validation (safe, zero database writes)
dry_run_summary = workflow.run_dry_run(exam_id=1, max_marks=30.0)
print("Dry-run passed:", dry_run_summary["dry_run_passed"])

# 6. Execute actual import with explicit secondary confirmation
if dry_run_summary["dry_run_passed"]:
    import_summary = workflow.confirm_and_import(
        confirmed_by="Prof. Sharma",
        import_confirmation=True,
    )
    print("Import status:", import_summary["import_status"])
    print(f"Saved: {import_summary['saved_records']}, Skipped ABS: {import_summary['skipped_absent']}")
```

---

## Testing

The PDF processing module contains **10 comprehensive test suites** covering all unit, integration, UI, and end-to-end database workflows.

### Run All Test Suites

```powershell
# Run the entire test suite sequentially
$tests = Get-ChildItem tests\test_*.py
foreach ($t in $tests) {
    Write-Host "=== Running $($t.Name) ===" -ForegroundColor Cyan
    & .venv\Scripts\python.exe $t.FullName
    if ($LASTEXITCODE -ne 0) {
        Write-Error "FAILED: $($t.Name)"
        break
    }
}
```

### Test Coverage Breakdown

| Test File | Test Count | What It Verifies |
|---|---|---|
| `test_extractor.py` | Unit | PDF stream extraction and missing file handling |
| `test_parser.py` | Integration | Parses 52 students, headers, and metadata from sample PDF |
| `test_normalizer.py` | 2 tests | Structure A compliance, roll uppercase, whitespace collapsing |
| `test_review.py` | 2 tests | Working draft isolation, inline student edits, error blocking |
| `test_end_to_end.py` | 3 tests | Full pipeline transformation from PDF to Structure B |
| `test_backend_client.py` | 8 tests | HTTP client, payload validation, timeouts, connection errors |
| `test_import_workflow.py` | 47 tests | Gated import, duplicate protection, uncertain timeout handling |
| `test_workflow_adapter.py` | 31 tests | Stateless adapter transitions across all 6 workflow stages |
| `test_pdf_upload_tab.py` | 8 tests | Streamlit UI component rendering, form validation, and buttons |
| `test_e2e_backend_integration.py` | 5 phases / 8 errors | Real PDF-to-SQLite database verification, dry-run 0 writes, 251 saved, 9 ABS skipped |

---

## Integration Specifications

### 1. Data Contracts

- **Structure A (Canonical Internal Document)**: Defined in detail in [`pdf_processing/PDF_INPUT_SPECIFICATION.md`](pdf_processing/PDF_INPUT_SPECIFICATION.md).
- **Structure B (Relational Backend Import Payload)**:
  ```json
  {
    "exam_id": 1,
    "max_marks": 30.0,
    "records": [
      {
        "roll_number": "0112AL251001",
        "subject_code": "BT-101",
        "marks": 28
      },
      {
        "roll_number": "0112AL251015",
        "subject_code": "BT-103",
        "marks": "ABS"
      }
    ]
  }
  ```

### 2. Backend Endpoint Compatibility

- **Endpoint**: `POST /marks/import?dry_run={true|false}`
- **Response Format**:
  ```json
  {
    "total_records": 260,
    "saved_records": 251,
    "skipped_absent": 9,
    "failed_records": 0,
    "saved": [...],
    "absent": [...],
    "errors": []
  }
  ```

### 3. Backend Recommendations

Refer to [`pdf_processing/BACKEND_CHANGES_REQUIRED.md`](pdf_processing/BACKEND_CHANGES_REQUIRED.md) for recommendations to wrap the backend SQLite import loop in a single atomic transaction and add a unique constraint on `marks(student_id, subject_id, exam_id)`.

---

## License

Institutional Academic Project &copy; 2026 StudentInsight Team. All rights reserved.