# JENNY

**Document Automation**

JENNY converts draft SOPs into properly formatted federal compliant documents. An LLM extracts structured content from the draft, then a deterministic Python pipeline handles all template mutation with a structural integrity gate. The pipeline is model-agnostic -- any LLM that produces a valid config can drive it.

## How It Works

```
Upload       User uploads the template (.docx) and source draft (.docx or .pdf)
Extract      LLM reads the draft and produces a structured config
Review       User verifies and edits the config in the browser UI
Generate     Pipeline mutates the template, validates output, produces .docx
```

Two extraction paths:
- **Keyed build** (`JENNY_keyed.exe`): Anthropic API key embedded -- extraction runs automatically
- **Keyless build** (`JENNY.exe`): User copies the extraction prompt into any LLM (ChatGPT, Gemini, Copilot, etc.) and pastes the output back

See `QUICKSTART.md` for end-user instructions.

## What Gets Extracted

From the source draft, JENNY extracts or derives:

| Section | Source |
|---------|--------|
| Title, Purpose | Verbatim from draft |
| Scope | Verbatim if present, otherwise derived from step content |
| Step-by-step instructions (S6) | Verbatim text with hierarchy assignment |
| Images / Screenshots | Extracted from .docx or .pdf, positioned at original locations |
| Hyperlinks | Extracted and preserved in output |
| Highlighted steps | Detected from .docx formatting, flagged for review |
| Roles, Materials, Guidelines | Derived from S6 content by the LLM |
| Cover date | From source, or defaults to current month/year |

LLM-derived sections (Scope, Roles, Materials, Guidelines, Hierarchy) require SOP owner review.

## Standalone Executables

JENNY ships as a single `.exe` -- no Python, Node.js, or environment setup required.

| Executable | Description |
|------------|-------------|
| `JENNY_keyed.exe` | API key embedded. Double-click and go. |
| `JENNY.exe` | No key. User extracts via external LLM and pastes config back. |

Place the `.exe` in its own folder and double-click. A browser window opens at `http://localhost:5000`. The app creates `uploads/` and `jobs/` folders next to the exe at runtime.

## Prototype Status

Current prototype validates against 82-84 checks and scores 100% on tested SOPs:

| Draft | Type | Score | Features |
|-------|------|-------|----------|
| DTS Job Aid (Cancelling Training Event) | PDF | 82/82 (100%) | Images, hyperlinks |
| CBA Reconciliation | DOCX | 83/83 (100%) | Highlights, nested hierarchy |
| Travel Memo | DOCX | 83/83 (100%) | Baseline text-only |
| Onboarding Travel Tracker | DOCX | In progress | Highlights, complex hierarchy |

### What Works
- Full extraction-to-docx pipeline for both .docx and .pdf drafts
- Image extraction, positioning, and embedding (PDF and DOCX)
- Hyperlink preservation
- Highlight detection from .docx and application to config
- Cover page uses full title, all other locations use short title
- External LLM flow: copy prompt with draft text + image markers, paste config back
- Config review UI with sequential numbering, section labels, editable fields
- Validation gate with score reporting
- Single-file executables (keyed and keyless)

### Known Limitations
- PDF text extraction depends on PyMuPDF -- scanned/image-only PDFs not supported
- Multi-procedure SOPs (`structure_type: "multi"`) not yet implemented
- External LLM cannot detect highlights -- JENNY splices them from the uploaded draft
- Step hierarchy is an LLM judgment call and may need manual correction

## Development Setup

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

**Build executables:**
```
pip install pyinstaller
python build.py
```

## File Structure

```
JENNY/
  README.md
  QUICKSTART.md                         End-user guide
  requirements.txt
  build.py                              Build script for executables
  jenny.spec                            PyInstaller spec
  .env                                  API key (not committed)
  backend/
    jenny_backend.py                    Flask API + session management
    jenny_pipeline.py                   Deterministic template mutation
    unpack_docx.py                      Unpack .docx to XML
    pack_docx.py                        Pack XML to .docx
    JENNY_Phase0_Extraction_Prompt.md   Extraction prompt (single source of truth)
  frontend/
    src/App.jsx                         React UI
    index.html
    package.json
  data/                                 Test drafts and templates
  dist/                                 Built executables (not committed)
```

## API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Status check |
| `/api/upload` | POST | Upload template and draft |
| `/api/extract` | POST | LLM extracts config from draft (keyed build) |
| `/api/get-prompt` | POST | Get assembled prompt for external LLM (keyless build) |
| `/api/import-config` | POST | Import config from external LLM output |
| `/api/generate` | POST | Run pipeline, return validated .docx |
| `/api/download/<job_id>` | GET | Download generated .docx |
| `/api/image/<session_id>/<filename>` | GET | Serve extracted image |
| `/api/key-status` | GET | Check API key and build type |

## Security

- No `exec()` -- all config parsing uses `ast.literal_eval`
- Debug mode disabled by default
- 50 MB upload size limit
- Server-side error logging only
- Path traversal protection on image serving endpoint
