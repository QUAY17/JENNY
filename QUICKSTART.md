# JENNY Quickstart Guide

## Getting Started

Place `JENNY.exe` in its own folder and double-click to launch. A browser window opens automatically.

## What You Need

- **FEMA SOP Template** (.docx) -- the standard FEMA template
- **Source SOP Draft** (.docx or .pdf) -- the draft you want to convert

## How It Works

### Step 1: Upload Files

Upload both files in the JENNY interface:
- The **FEMA SOP Template** (the formatted template)
- Your **Source SOP Draft** (the content to extract)

### Step 2: Extract Config

Click **EXTRACT WITH EXTERNAL LLM**. This opens a two-step dialog:

1. **Copy the prompt** -- Click "COPY PROMPT" to copy the extraction instructions + your draft text to your clipboard
2. **Paste into your LLM** -- Open ChatGPT, Gemini, Copilot, or any other LLM. Paste the prompt. Also attach your source draft file if the LLM supports file uploads.
3. **Copy the output** -- The LLM will return a Python config block. Copy the entire output.
4. **Paste it back** -- Paste the LLM output into the text box in JENNY and click "IMPORT"

### Step 3: Review

JENNY shows the extracted config for review. Check:
- **Title** -- full title (cover page) and short title (headers/sections)
- **Cover Date** -- defaults to the current month if not in the source
- **Steps** -- verify numbering and hierarchy (1. a. i.)
- **Highlighted steps** -- appear with a colored border (these need SOP owner attention)
- **Roles, Materials, Guidelines** -- these are LLM-derived and need human review

Edit any field directly in the UI before generating.

### Step 4: Generate

Click **GENERATE SOP**. JENNY runs the pipeline and validates the output. A score of 100% means all checks passed.

Click **DOWNLOAD .DOCX** to save the final document.

Click **NEW SOP** to start over with a different draft.

## Tips

- The LLM extracts text content only -- images, hyperlinks, and highlights are handled automatically by JENNY from your uploaded draft file. This is why you must upload the draft in both places.
- If the LLM misses steps or gets the hierarchy wrong, fix it in the review screen before generating.
- Highlighted steps from the source draft appear highlighted in the review -- these flag content the SOP owner should verify.
- For best results with ChatGPT, use GPT-4o or GPT-4. The extraction prompt is optimized for these models.
