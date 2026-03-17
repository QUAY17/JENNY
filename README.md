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

## Standalone Executables

JENNY ships as a single `.exe` file -- no Python, Node.js, or environment setup required.

**Two variants:**

| Executable | Description |
|------------|-------------|
| `JENNY_keyed.exe` | Anthropic API key embedded. Double-click and go. |
| `JENNY.exe` | No key. User extracts config via any external LLM (ChatGPT, Gemini, etc.) and pastes it back. See `QUICKSTART.md`. |

**Usage:** Place the `.exe` in its own folder and double-click. A browser window opens automatically to `http://localhost:5000`. The app creates `uploads/` and `jobs/` folders next to the exe at runtime.

**Building executables:**
```
pip install pyinstaller
python build.py
```
This builds the frontend, then produces both `dist/JENNY.exe` and `dist/JENNY_keyed.exe`. The keyed build reads the API key from `.env`.

## Stack

- **Backend:** Python (Flask) -- `jenny_backend.py`
- **Frontend:** React (Vite) -- `App.jsx`
- **Pipeline:** Python (stdlib only) -- `jenny_pipeline.py`, `pack_docx.py`, `unpack_docx.py`
- **Build:** PyInstaller (`build.py` + `jenny.spec`)

## Setup (Development)

**Backend:**
```
pip install -r requirements.txt
set ANTHROPIC_API_KEY=sk-ant-...
cd backend
python jenny_backend.py
```

**Frontend:**
```
cd frontend
npm install
npm run dev
```

Backend runs on `http://localhost:5000`. Frontend dev server runs on `http://localhost:5173`.

## File Structure

```
JENNY/
  README.md
  requirements.txt
  build.py                              Build script for executables
  jenny.spec                            PyInstaller spec
  .env                                  API key (not committed)
  backend/
    jenny_backend.py                    Flask API (9 endpoints)
    jenny_pipeline.py                   Deterministic template mutation
    unpack_docx.py                      Unpack .docx to XML
    pack_docx.py                        Pack XML to .docx
    JENNY_Phase0_Extraction_Prompt.md   Phase 0 prompt (loaded at runtime)
    QUICKSTART.md                       End-user guide for JENNY.exe
  frontend/
    src/App.jsx                         React UI
    index.html
    package.json
  dist/                                 Built executables (not committed)
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
| `/api/image/<session_id>/<filename>` | GET | Serve extracted image from draft |
| `/api/key-status` | GET | Check if API key is configured |
| `/api/set-key` | POST | Set API key at runtime (keyless mode) |

## Workflow

1. **Upload** -- Template (.docx) and draft (.docx or .pdf)
2. **Extract or Import** -- LLM extracts config via backend API, or user imports config from external LLM
3. **Review** -- User edits config in frontend: hierarchy, text, highlights, roles, materials, guidelines
4. **Generate** -- Pipeline mutates template, validates against 84 checks
5. **Download** -- User downloads the .docx

LLM-generated sections (Scope, Roles, Materials, Guidelines, Hierarchy) require SOP owner review before approval.

## Image/Screenshot Support

Draft SOPs often contain screenshots in their step-by-step instructions. JENNY extracts these from both `.docx` and `.pdf` drafts, displays them in the review UI at the correct position within the S6 steps, and embeds them in the generated output.

- **Extraction:** Images are pulled from the draft during Phase 0 and spliced into `s6_steps` at their original positions
- **Review:** Thumbnails display inline with text steps; ilvl (indentation level) is editable; images can be deleted
- **Output:** Images are embedded in the output `.docx` with proper OOXML structure, capped at ~4 inches wide, indented to match their ilvl
- **PDF filtering:** Skips logos, seals, and tiny icons; preserves UI screenshots and dialog boxes

Image steps in the config:
```python
{"type": "image", "src": "image1.png", "ilvl": 0, "width_emu": 3657600, "height_emu": 2743200}
```

## Security

- No `exec()` -- all config parsing uses `ast.literal_eval` (safe literal evaluation only)
- Debug mode disabled by default (set `FLASK_DEBUG=1` to enable)
- 50 MB upload size limit
- Server-side error logging only (no tracebacks sent to client)
- Path traversal protection on image serving endpoint

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
| `s6_steps` | object[] | `{ text, ilvl (0-3), highlighted, highlight_color }` or `{ type: "image", src, ilvl, width_emu, height_emu }` |
| `s4_roles` | string[] | `"Role: Description"` derived from S6 |
| `s5_materials` | string | Comma-separated list derived from S6 |
| `s7_guidelines` | string[] | Compliance guidelines derived from S6 |
| `s3_supersession` | string | Supersession statement |
| `extraction_notes` | string[] | Flags for SOP owner review |
