# JENNY

**FEMA SOP Document Generator**

JENNY converts draft SOPs into properly formatted FEMA-compliant documents. Phase 0 uses any LLM to extract structured content from the draft. The deterministic Python pipeline handles all template mutation with an 84-check structural integrity gate. The pipeline is model-agnostic -- any LLM that produces a valid config can drive it.

88% cost reduction vs monolithic LLM generation ($0.02-$0.05 per SOP vs $1.50-$2.40).

## Architecture

```
Phase 0 (LLM):          Any LLM extracts draft content into a config dict
Phase 1+ (Pipeline):    Python mutates the FEMA template from the config (zero tokens)
```

Three input paths for Phase 0:
- **Plan A:** Backend calls Anthropic API directly
- **Plan B:** Client's own LLM endpoint generates the config, imported into JENNY
- **Plan C:** User pastes the Phase 0 prompt into any chatbot, imports the output

## Stack

- **Backend:** Python (Flask) -- `jenny_backend.py`
- **Frontend:** React (Vite) -- `jenny_frontend.jsx`
- **Pipeline:** Python (stdlib only) -- `jenny_pipeline.py`, `pack_docx.py`, `unpack_docx.py`

## Setup

**Backend:**
```
cd backend
pip install flask flask-cors
pip install pdfminer.six
set ANTHROPIC_API_KEY=sk-ant-...
python jenny_backend.py
```

**Frontend:**
```
cd frontend
npm install
npm run dev
```

Backend runs on `http://localhost:5000`. Frontend runs on `http://localhost:5173`.

## File Structure

```
JENNY/
  README.md
  .gitignore
  backend/
    jenny_backend.py                    Flask API (7 endpoints)
    jenny_pipeline.py                   Deterministic template mutation (825 lines)
    unpack_docx.py                      Unpack .docx to XML
    pack_docx.py                        Pack XML to .docx
    JENNY_Phase0_Extraction_Prompt.md   Phase 0 prompt (loaded at runtime)
    JENNY_Phase0_Chatbot_Prompt.md      Single-paste prompt for Plan C
  frontend/
    src/App.jsx                         React UI
    package.json
```

The FEMA template is uploaded by the user, not bundled with the code.

## API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Status check |
| `/api/upload` | POST | Upload template (.docx) and draft (.docx or .pdf) |
| `/api/extract` | POST | Phase 0: LLM extracts config from draft |
| `/api/import-config` | POST | Import config from external LLM (Plan B/C) |
| `/api/sanitize` | POST | Sanitize a config |
| `/api/generate` | POST | Run pipeline, return validated .docx |
| `/api/download/<job_id>` | GET | Download generated .docx |

## Workflow

1. **Upload** -- Template (.docx) and draft (.docx or .pdf)
2. **Extract or Import** -- LLM extracts config via backend API, or user imports config from external LLM
3. **Review** -- User edits config in frontend: hierarchy, text, highlights, roles, materials, guidelines
4. **Generate** -- Pipeline mutates template, validates against 84 checks
5. **Download** -- User downloads the .docx

LLM-generated sections (Scope, Roles, Materials, Guidelines, Hierarchy) require SOP owner review before approval.

## Validation Gate

84 structural checks across 11 categories:

- **XML (4)** -- document and header parse, no double-encoded ampersands
- **Placeholders (8)** -- all template markers removed
- **Header (4)** -- format, separator, no highlight bleed
- **Title (3)** -- full title, short title, header consistent
- **Structure (7)** -- Sections 1-8 headings present
- **Colons (4)** -- heading colons removed per FEMA style
- **S6 Steps (18-20)** -- ilvl counts match config, first 8 steps verbatim, highlights accurate
- **Intelligent Completion (10-11)** -- S2/S4/S5/S7/S8 populated with substantive content
- **Review Flags (15)** -- 5 flags with italic + yellow highlight formatting
- **Page Breaks (1)** -- none in S6
- **Revision (4)** -- author, version, description

## Config Format

Python dict with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `full_title` | string | Full SOP title (`&` encoded as `&amp;`) |
| `short_title` | string | Procedure name (`&` encoded as `&amp;`) |
| `structure_type` | string | `"single"` or `"multi"` |
| `cover_date` | string | `"February 2026"` (defaults to current month/year) |
| `purpose` | string | Verbatim from source |
| `scope` | string | Verbatim or derived from S6 |
| `s6_intro` | string | Text before Step 1 |
| `s6_steps` | object[] | `{ text, ilvl (0-3), highlighted, highlight_color }` |
| `s4_roles` | string[] | `"Role: Description"` derived from S6 |
| `s5_materials` | string | Comma-separated list derived from S6 |
| `s7_guidelines` | string[] | Compliance guidelines derived from S6 |
| `s3_supersession` | string | Supersession statement |
| `extraction_notes` | string[] | Flags for SOP owner review |