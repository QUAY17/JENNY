# JENNY

**Templated Document Generator**

JENNY automates the conversion of draft SOPs into properly formatted FEMA-compliant documents. JENNY can be paired with ANY LLM for structured content extraction because the heavy lifting is done by a deterministic Python pipeline for template mutation, achieving 100% validation accuracy with a 79-check structural integrity gate.

## Cost Savings

The JENNY pipeline approach reduces token usage by 88%:

| Metric | Opus Monolithic | Pipeline (Sonnet Phase 0) |
|--------|----------------|--------------------------|
| Per SOP | $1.50 - $2.40 | $0.02 - $0.05 |
| Batch of 50 | $75 - $120 | $1.12 - $2.48 |
| Annual (200 SOPs) | $600 - $960 | $4.50 - $10.00 |

Opus pricing for monolithic because Opus is the only model that achieves 100% accuracy end-to-end. Sonnet pricing for pipeline Phase 0 extraction. The pipeline itself is zero tokens (deterministic Python execution).

## Architecture

```
User uploads:                     Backend:                        Output:
  FEMA Template (.docx)   --->   /api/upload        (store)
  Source Draft (.docx|.pdf) -->   /api/extract       (LLM)   ---> Config dict
                                  /api/generate      (pipeline) -> Validated .docx
                                  /api/download      (serve)  ---> User downloads
```

**Phase 0 (LLM):** Extracts structured content from the source draft into a config dict. The backend loads the Phase 0 prompt from `JENNY_Phase0_Extraction_Prompt.md`, extracts text from the draft with `[ilvl=N]` and `[highlight=color]` markers (for .docx) or plain text (for .pdf), and sends to the LLM. Hierarchy is assigned based on FEMA SOP template conventions (`1. > a. > i. > 1.`), not the draft's formatting. Roles, materials, and guidelines are derived from the procedure steps. The backend sanitizes the config (ampersand encoding, ilvl validation, cover date default, highlight_color, newline stripping) before pipeline execution.

**Phase 1+ (Deterministic):** The Python pipeline unpacks the FEMA template, performs all XML mutations from the config, inserts review flags, removes page breaks, updates headers, and validates the output against 79 structural checks. No LLM involvement. Supports 4-level hierarchy (ilvl 0-3) and multiple highlight colors (yellow, cyan, etc.).

## API

| Step | Endpoint | Method | Input | Output |
|------|----------|--------|-------|--------|
| Upload | `/api/upload` | POST | FormData with template (.docx) and/or draft (.docx or .pdf) | `{ session_id, template: bool, draft: bool }` |
| Extract | `/api/extract` | POST | `{ session_id }` | `{ config, issues, stats, draft_chars, model }` |
| Generate | `/api/generate` | POST | `{ session_id, config }` | `{ success, job_id, score, log, download_url }` |
| Download | `/api/download/<job_id>` | GET | -- | .docx file |
| Health | `/api/health` | GET | -- | `{ status, version }` |

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+ (frontend)
- Anthropic API key (or any LLM API key for Phase 0 extraction)

### Backend

```bash
cd backend/
pip install flask flask-cors
pip install pdfminer.six          # optional: PDF draft support
export ANTHROPIC_API_KEY=sk-ant-...
python jenny_backend.py
```

Server starts on `http://localhost:5000`.

### Frontend

```bash
cd frontend/
npm install
npm run dev
```

Frontend starts on `http://localhost:5173` and connects to the backend at `http://localhost:5000`.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes (for default config) | Anthropic API key for Phase 0 extraction |

## File Structure

```
JENNY/
  backend/
    jenny_backend.py                    Flask API server (6 endpoints)
    jenny_pipeline.py                   Deterministic template mutation engine (777 lines)
    unpack_docx.py                      Unpack .docx to XML directory
    pack_docx.py                        Pack XML directory to .docx
    JENNY_Phase0_Extraction_Prompt.md   Phase 0 system + user prompts with CBA reference example
  frontend/
    src/App.jsx                         React frontend (copy of jenny_frontend.jsx)
    package.json                        Vite + React dependencies
```

The FEMA SOP template (`JENNYS_SOP_Template.docx`) is uploaded by the user through the frontend, not bundled with the code.

## Workflow

1. **Upload** -- User provides the FEMA template (.docx) and a source SOP draft (.docx or .pdf).
2. **Extract** -- Backend loads the Phase 0 prompt, reads the draft, sends structured text to Claude Sonnet 4.6, receives a Python config. Config is parsed and sanitized automatically.
3. **Review** -- User reviews and edits the extracted config in the frontend. Step hierarchy (ilvl 0-3), text, highlights, roles, materials, and guidelines are all editable. User-friendly labels show the FEMA numbering conventions: `1. 2. 3.` = Main Step, `a. b. c.` = Sub-step, `i. ii. iii.` = Sub-sub, `1. 2. 3.` (nested) = Sub-sub-sub.
4. **Generate** -- Backend runs the deterministic pipeline. Template is unpacked, XML is mutated, output is validated against 79 checks, and the .docx is packed.
5. **Download** -- User downloads the validated SOP.

## Validation Gate

The pipeline runs 81-84 structural checks (count varies by SOP complexity):

- **XML (4)** -- document.xml and header5.xml parse, no double-encoded ampersands
- **Placeholders (8)** -- all template markers removed from body and header
- **Header (4)** -- hyphen separator, no highlight bleed, no en-dash, single separator
- **Title (3)** -- full title, short title, and header are consistent
- **Structure (7)** -- Sections 1-8 headings present
- **Colons (4)** -- section heading colons removed per FEMA style
- **S6 Steps (18-20)** -- template remnants gone, ilvl 0/1/2/3 counts match config, total document ilvl counts correct, first 8 steps verified verbatim, highlight count accurate, intro paragraph validated
- **Intelligent Completion (10-11)** -- S2 scope populated or flagged, S4 roles populated with Role:Description format, S5 materials populated with substantive content, S7 guidelines populated with substantive content, S8 revision history populated with generation date
- **Review Flags (15)** -- 5 flags (S2, S4, S5, S7, S8) each verified for existence, pPr italic+highlight, rPr italic+highlight
- **Page Breaks (1)** -- no stray page breaks in S6
- **Revision (4)** -- JENNY author tag, author format, version 1.0, initial SOP description

## LLM Model

Phase 0 extraction uses Claude Sonnet 4.6 (`claude-sonnet-4-6`) via the Anthropic API. The model is configured in `jenny_backend.py`. To swap models, change the `model_used` variable in the `/api/extract` endpoint.

The pipeline itself is model-agnostic. Any LLM that produces a valid config dict can drive the pipeline. PDF drafts lose structural metadata (no `[ilvl=N]` markers), so hierarchy assignment relies entirely on content inference.

## Config Format

The config is a Python dict with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `full_title` | string | Full SOP title. `&` encoded as `&amp;` |
| `short_title` | string | Procedure name. `&` encoded as `&amp;` |
| `structure_type` | string | `"single"` or `"multi"` |
| `cover_date` | string | e.g. `"February 2026"`. Defaults to current month/year |
| `author` | string | `"JENNY Sonnet 4.6"` (set by backend from model used) |
| `gen_date` | string | `"MM/DD/YYYY"` |
| `extraction_notes` | string[] | Flags for SOP owner review |
| `purpose` | string | Verbatim from source |
| `scope` | string | Verbatim or derived from S6 |
| `s6_intro` | string | Text before Step 1 (no numbering) |
| `s6_steps` | object[] | `{ text, ilvl (0-3), highlighted (bool), highlight_color (string) }` |
| `s4_roles` | string[] | `"Role: Description"` derived from S6 |
| `s5_materials` | string | Comma-separated list derived from S6 |
| `s7_guidelines` | string[] | Compliance guidelines derived from S6 |
| `s3_supersession` | string | Supersession statement |

## Phase 0 Prompt

The extraction prompt (`JENNY_Phase0_Extraction_Prompt.md`) contains:

- **System message**: 10 critical rules covering verbatim extraction, hierarchy assignment, highlight detection, ampersand encoding, structure type, derived sections (S4/S5/S7), scope generation, and extraction notes.
- **User message**: Config template structure, field descriptions, and a complete CBA Reconciliation reference example showing correct format and level of detail for all fields.

The prompt is loaded from file at runtime, not hardcoded in the backend. Updates to the prompt take effect on the next extraction without redeploying code.

## Draft Format Support

| Format | Structural Metadata | Hierarchy Source | Highlight Detection |
|--------|-------------------|-----------------|-------------------|
| .docx | `[ilvl=N]` markers from XML | Markers as hints + content inference | Colors from XML |
| .pdf | None | Content inference only | Not available (flagged in extraction_notes) |

PDF support requires one of: `pdftotext` (poppler-utils), `pdfminer.six`, or `PyPDF2`. Install with `pip install pdfminer.six`.
