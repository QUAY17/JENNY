# JENNY

**Templated Document Generator**

JENNY automates the conversion of draft SOPs into properly formatted FEMA-compliant documents. JENNY can be paired with *ANY* LLM for structured content extraction because the heavy lifting is done by the deterministic Python pipeline for template mutation, achieving 100% validation accuracy with a 77-check structural integrity gate.

The JENNY pipeline approach uses roughly 10-15% of the tokens compared to monolithic AI generation, reducing token counts by 
---

## Architecture

```
User uploads:                     Backend:                        Output:
  FEMA Template (.docx)   --->   /api/upload        (store)
  Source Draft (.docx)     --->   /api/extract       (LLM)   ---> Config JSON
                                  /api/generate      (pipeline) -> Validated .docx
                                  /api/download      (serve)  ---> User downloads
```

**Phase 0 (LLM):** Any model extracts structured content from the source draft into a config dict. Hierarchy, roles, materials, and guidelines are derived from the procedure steps. The backend sanitizes the config (ampersand encoding, ilvl validation, newline stripping) before pipeline execution.

**Phase 1+ (Deterministic):** The Python pipeline unpacks the FEMA template, performs all XML mutations from the config, inserts review flags, removes page breaks, updates headers, and validates the output against 77 structural checks. No LLM involvement. No creative decisions.

---

## API

| Step | Endpoint | Method | Input | Output |
|------|----------|--------|-------|--------|
| Upload | `/api/upload` | POST | FormData with `template` and/or `draft` (.docx) | `{ session_id, template: bool, draft: bool }` |
| Extract | `/api/extract` | POST | `{ session_id }` | `{ config, issues, stats, draft_chars }` |
| Generate | `/api/generate` | POST | `{ session_id, config }` | `{ success, job_id, score, log, download_url }` |
| Download | `/api/download/<job_id>` | GET | -- | `.docx` file |
| Health | `/api/health` | GET | -- | `{ status, version }` |

---

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+ (frontend)
- LLM API key*

### Backend

```bash
cd jenny
pip install flask flask-cors
export ANTHROPIC_API_KEY=sk-ant-...
python jenny_backend.py
```

Server starts on `http://localhost:5000`.

### Environment Variables (optional)

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | No | Anthropic API key for Phase 0 extraction |
| `OPENAI_API_KEY` | No | Open AI API key for Phase 0 extraction |



### Frontend

The React frontend connects to the backend at `http://localhost:5000`. Update `API_BASE` in `jenny_frontend.jsx` if the backend runs elsewhere.

---

## File Structure

```
jenny/
  jenny_backend.py              Flask API server
  jenny_pipeline.py             Deterministic template mutation engine (708 lines)
  jenny_frontend.jsx            React frontend
  unpack_docx.py                Unpack .docx to XML directory
  pack_docx.py                  Pack XML directory to .docx
  JENNY_Phase0_Extraction_Prompt.md   Phase 0 system + user prompts
  JENNYS_SOP_Template.docx      FEMA SOP template (required input)
```

---

## Workflow

1. **Upload** -- User provides the FEMA template and a source SOP draft.
2. **Extract** -- Backend reads the draft .docx XML, sends text to Claude 3.7 Sonnet, receives structured config JSON. Config is sanitized automatically.
3. **Review** -- User reviews and edits the extracted config in the frontend. Step hierarchy (ilvl), roles, materials, and guidelines are all editable.
4. **Generate** -- Backend runs the deterministic pipeline. Template is unpacked, XML is mutated, output is validated against 77 checks, and the .docx is packed.
5. **Download** -- User downloads the validated SOP.

---

## Validation Gate

The pipeline runs 77 structural checks covering:

- XML validity (document + header)
- Placeholder removal (8 template markers)
- Header formatting (separator, no highlight, no en-dash)
- Title cascade (full title, short title, header)
- FEMA heading structure (Sections 1-8)
- Section heading colon removal
- Section 6 hierarchy preservation (ilvl0/ilvl1/ilvl2 counts)
- Section 6 content integrity (first 8 steps verified)
- Highlight count accuracy
- Intelligent completion (S4 roles, S5 materials populated)
- Review flags (5 flags with italic + yellow highlight formatting)
- Page break removal
- Revision history (JENNY author tag, version, description)

---

## LLM Model

Phase 0 extraction currently uses **Claude 3.7 Sonnet** (`claude-3-7-sonnet-20250219`) via the Anthropic API. The model is configured in `jenny_backend.py`. To swap models, change the `model` field in the `/api/extract` endpoint.

The pipeline itself is model-agnostic. Any LLM that produces a valid config dict can drive the pipeline.

---

## Config Format

The config is a Python dict (or JSON) with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `full_title` | string | Full SOP title. `&` encoded as `&amp;` |
| `short_title` | string | Procedure name. `&` encoded as `&amp;` |
| `structure_type` | string | `"single"` or `"multi"` |
| `cover_date` | string | e.g. `"February 2026"` |
| `author` | string | `"JENNY-v13"` |
| `gen_date` | string | `"MM/DD/YYYY"` |
| `extraction_notes` | string[] | Flags for SOP owner review |
| `purpose` | string | Verbatim from source |
| `scope` | string | Verbatim or derived from S6 |
| `s6_intro` | string | Text before Step 1 (no numbering) |
| `s6_steps` | object[] | `{ text, ilvl (0-2), highlighted (bool) }` |
| `s4_roles` | string[] | `"Role: Description"` derived from S6 |
| `s5_materials` | string | Comma-separated list derived from S6 |
| `s7_guidelines` | string[] | Compliance guidelines derived from S6 |
| `s3_supersession` | string | Supersession statement |
