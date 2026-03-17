#!/usr/bin/env python3
"""
JENNY SOP Generator - Backend Server
Flask API that orchestrates:
  1. File upload (template + draft)
  2. Phase 0 extraction (calls LLM API for config generation)
  3. Config sanitization
  4. Phase 1+ pipeline execution (deterministic)
  5. Output delivery (.docx download)
"""

import os, sys, json, shutil, tempfile, uuid, subprocess, re, traceback, ast
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import urllib.request

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB upload limit

# Configuration
# When running as PyInstaller exe, _MEIPASS has bundled data files;
# writable dirs (uploads/jobs) go next to the exe, not inside _MEIPASS.
if getattr(sys, '_MEIPASS', None):
    PIPELINE_DIR = Path(sys._MEIPASS)
    _BASE = Path(sys.executable).parent
else:
    PIPELINE_DIR = Path(__file__).parent
    _BASE = Path(".")
UPLOAD_DIR = _BASE / "uploads"
JOBS_DIR = _BASE / "jobs"
UPLOAD_DIR.mkdir(exist_ok=True)
JOBS_DIR.mkdir(exist_ok=True)

# API Key -- build.py patches EMBEDDED_API_KEY for keyed builds
EMBEDDED_API_KEY = None
ANTHROPIC_API_KEY = EMBEDDED_API_KEY or os.environ.get("ANTHROPIC_API_KEY")

# Store uploaded files per session
sessions = {}


# ============================================================
# HELPERS
# ============================================================

def parse_config_safely(text):
    """Parse a JENNY_CONFIG dict from text using ast.literal_eval (no exec).

    Handles:
      - JENNY_CONFIG = { ... }   (Python assignment)
      - { ... }                  (bare dict literal)
      - markdown fences around either form
    Returns the parsed dict, or raises ValueError on failure.
    """
    cleaned = text.strip()
    # Strip markdown fences
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```\w*\n', '', cleaned)
        cleaned = re.sub(r'\n```\s*$', '', cleaned)

    # If it contains an assignment, extract the RHS
    m = re.search(r'JENNY_CONFIG\s*=\s*(\{[\s\S]*\})\s*$', cleaned)
    if m:
        dict_text = m.group(1)
    else:
        # Try to find a bare dict literal
        m2 = re.search(r'(\{[\s\S]*\})', cleaned)
        if m2:
            dict_text = m2.group(1)
        else:
            raise ValueError("No dict literal found in text")

    return ast.literal_eval(dict_text)


def sanitize_config(config):
    """Fix common LLM extraction issues before pipeline runs."""
    issues = []

    # Ampersand encoding in titles
    for field in ["full_title", "short_title"]:
        if field in config and "&" in config[field] and "&amp;" not in config[field]:
            config[field] = config[field].replace("&", "&amp;")
            issues.append(f"Encoded & as &amp; in {field}")

    # Don't double-encode
    for field in ["full_title", "short_title"]:
        if field in config:
            while "&amp;amp;" in config[field]:
                config[field] = config[field].replace("&amp;amp;", "&amp;")
                issues.append(f"Fixed double-encoded ampersand in {field}")

    # Strip newlines from titles
    for field in ["full_title", "short_title"]:
        if field in config and "\n" in config[field]:
            config[field] = config[field].replace("\n", " ").strip()
            issues.append(f"Stripped newline from {field}")

    # Validate ilvl values and ensure highlight_color
    if "s6_steps" in config:
        for i, step in enumerate(config["s6_steps"]):
            # Default type to "text" if missing (backwards compat)
            if "type" not in step:
                step["type"] = "text"

            if step.get("type") == "image":
                # Only validate ilvl for images
                if not isinstance(step.get("ilvl"), int) or step["ilvl"] not in (0, 1, 2, 3):
                    step["ilvl"] = 0
                continue

            if not isinstance(step.get("ilvl"), int) or step["ilvl"] not in (0, 1, 2, 3):
                config["s6_steps"][i]["ilvl"] = 0
                issues.append(f"Reset invalid ilvl to 0 for step {i}")
            if "highlighted" not in step:
                config["s6_steps"][i]["highlighted"] = False
            if "highlight_color" not in step:
                config["s6_steps"][i]["highlight_color"] = "yellow"

    # Validate structure_type
    if config.get("structure_type") not in ("single", "multi"):
        config["structure_type"] = "single"
        issues.append("Reset invalid structure_type to 'single'")

    # Leave cover_date empty if not found — user must fill it in
    if not config.get("cover_date") or config["cover_date"].strip() == "":
        config["cover_date"] = ""
        issues.append("No cover_date found in source. Please set the cover date.")

    # Ensure required fields exist
    defaults = {
        "author": "JENNY",
        "gen_date": datetime.now().strftime("%m/%d/%Y"),
        "s3_supersession": "This document does not supersede any existing FEMA doctrine.",
        "extraction_notes": [],
    }
    for k, v in defaults.items():
        if k not in config:
            config[k] = v
            issues.append(f"Added missing field: {k}")

    return config, issues


def write_config_py(config, path):
    """Write the config dict as a Python file the pipeline can import."""
    lines = ["# JENNY Config - Auto-generated by JENNY Frontend",
             f"# Generated: {datetime.now().isoformat()}",
             "",
             "JENNY_CONFIG = {"]

    for key, val in config.items():
        if isinstance(val, str):
            # Escape quotes in strings
            escaped = val.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'    "{key}": "{escaped}",')
        elif isinstance(val, list):
            if len(val) == 0:
                lines.append(f'    "{key}": [],')
            elif isinstance(val[0], dict):
                # s6_steps (text and image entries)
                lines.append(f'    "{key}": [')
                for item in val:
                    step_type = item.get("type", "text")
                    if step_type == "image":
                        src_esc = item["src"].replace("\\", "\\\\").replace('"', '\\"')
                        ilvl = item.get("ilvl", 0)
                        w = item.get("width_emu", 4572000)
                        h = item.get("height_emu", 3429000)
                        lines.append(f'        {{"type": "image", "src": "{src_esc}", "ilvl": {ilvl}, "width_emu": {w}, "height_emu": {h}}},')
                    else:
                        text_esc = item["text"].replace("\\", "\\\\").replace('"', '\\"')
                        ilvl = item.get("ilvl", 0)
                        hl = item.get("highlighted", False)
                        hl_color = item.get("highlight_color", "yellow")
                        step_dict = f'{{"type": "text", "text": "{text_esc}", "ilvl": {ilvl}, "highlighted": {hl}, "highlight_color": "{hl_color}"'
                        if item.get("hyperlinks"):
                            step_dict += f', "hyperlinks": {json.dumps(item["hyperlinks"])}'
                        step_dict += "}"
                        lines.append(f'        {step_dict},')
                lines.append("    ],")
            else:
                # string arrays
                lines.append(f'    "{key}": [')
                for item in val:
                    item_esc = str(item).replace("\\", "\\\\").replace('"', '\\"')
                    lines.append(f'        "{item_esc}",')
                lines.append("    ],")
        elif isinstance(val, bool):
            lines.append(f'    "{key}": {val},')
        elif isinstance(val, (int, float)):
            lines.append(f'    "{key}": {val},')
        else:
            lines.append(f'    "{key}": {json.dumps(val)},')

    lines.append("}")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def run_jenny_pipeline(config, template_path, output_path, job_dir, session_id=None):
    """Execute the JENNY pipeline in a job directory."""
    # Write config file
    config_path = job_dir / "jenny_config.py"
    write_config_py(config, config_path)

    # Copy pipeline files to job directory
    for f in ["jenny_pipeline.py", "unpack_docx.py", "pack_docx.py"]:
        src = PIPELINE_DIR / f
        if src.exists():
            shutil.copy2(src, job_dir / f)

    # Copy template
    shutil.copy2(template_path, job_dir / "TEMPLATE.docx")

    # Copy session images to job directory for pipeline access
    if session_id:
        src_images = UPLOAD_DIR / session_id / "images"
        if src_images.exists():
            dst_images = job_dir / "images"
            if dst_images.exists():
                shutil.rmtree(dst_images)
            shutil.copytree(str(src_images), str(dst_images))

    # Run pipeline
    output_file = job_dir / "OUTPUT.docx"

    if getattr(sys, '_MEIPASS', None):
        # In PyInstaller bundle: run in-process (sys.executable is the exe, not Python)
        import io, contextlib
        old_cwd = os.getcwd()
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        try:
            os.chdir(str(job_dir))
            sys.path.insert(0, str(job_dir))
            from jenny_pipeline import load_config, run_pipeline
            cfg = load_config("jenny_config.py")
            with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                run_pipeline(cfg, "TEMPLATE.docx", "OUTPUT.docx")
            return {
                "success": output_file.exists(),
                "stdout": stdout_capture.getvalue(),
                "stderr": stderr_capture.getvalue(),
                "output_path": str(output_file) if output_file.exists() else None,
                "returncode": 0,
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": stdout_capture.getvalue(),
                "stderr": f"{stderr_capture.getvalue()}\n{e}",
                "output_path": None,
                "returncode": 1,
            }
        finally:
            os.chdir(old_cwd)
            if str(job_dir) in sys.path:
                sys.path.remove(str(job_dir))
    else:
        result = subprocess.run(
            [sys.executable, "jenny_pipeline.py",
             "jenny_config.py",
             "TEMPLATE.docx",
             "OUTPUT.docx"],
            capture_output=True, text=True, cwd=str(job_dir),
            timeout=120,
        )
        return {
            "success": result.returncode == 0 and output_file.exists(),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "output_path": str(output_file) if output_file.exists() else None,
            "returncode": result.returncode,
        }


# ============================================================
# API ENDPOINTS
# ============================================================

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "JENNY v13 Backend"})


def _extract_draft_assets(session_id, draft_path):
    """Extract images and hyperlinks from a draft file at upload time.
    Stores results on the session so they're available for any flow."""
    if sessions[session_id].get("image_positions"):
        return  # Already extracted

    draft_path_lower = draft_path.lower()
    session_dir = UPLOAD_DIR / session_id
    images_dir = session_dir / "images"
    images_dir.mkdir(exist_ok=True)

    if draft_path_lower.endswith(".pdf"):
        image_positions = []
        hyperlinks = []
        try:
            import fitz
            pdf_doc = fitz.open(draft_path)
            total_pages = len(pdf_doc)
            img_counter = 0

            # Collect numbered step y-positions across all pages for image mapping
            step_y_positions = []  # (absolute_y, step_index)
            step_idx = 0
            for pn in range(total_pages):
                pg = pdf_doc[pn]
                pg_h = pg.rect.height
                blocks = pg.get_text('dict')['blocks']
                for block in blocks:
                    if 'lines' not in block:
                        continue
                    for line in block['lines']:
                        text = ''.join(span['text'] for span in line['spans']).strip()
                        if re.match(r'^\d+\.?\s', text):
                            abs_y = pn + (line['bbox'][1] / pg_h)
                            step_y_positions.append((abs_y, step_idx))
                            step_idx += 1

            for page_num in range(total_pages):
                page = pdf_doc[page_num]
                page_h = page.rect.height

                for img_info in page.get_image_info(xrefs=True):
                    xref = img_info.get("xref", 0)
                    bbox = img_info.get("bbox", (0, 0, 0, 0))
                    if not xref:
                        continue
                    render_w = bbox[2] - bbox[0]
                    render_h = bbox[3] - bbox[1]
                    y_frac = bbox[1] / page_h if page_h else 0
                    if render_w < 30 and render_h < 30:
                        continue
                    if page_num == 0 and y_frac < 0.15:
                        continue
                    try:
                        base_image = pdf_doc.extract_image(xref)
                        img_bytes = base_image["image"]
                        img_ext = base_image.get("ext", "png")
                        img_name = f"pdf_image_{img_counter}.{img_ext}"
                        (images_dir / img_name).write_bytes(img_bytes)

                        img_abs_y = page_num + (bbox[1] / page_h)

                        # Find the last numbered step above this image
                        after_step_idx = 0
                        for sy, si in step_y_positions:
                            if sy < img_abs_y:
                                after_step_idx = si
                            else:
                                break

                        image_positions.append({
                            "src": img_name,
                            "width_emu": int(render_w * 12700),
                            "height_emu": int(render_h * 12700),
                            "position_frac": img_abs_y / max(total_pages, 1),
                            "after_step_idx": after_step_idx,
                        })
                        img_counter += 1
                    except Exception:
                        continue

                # Hyperlinks
                for link in page.get_links():
                    if link.get("kind") == 2 and link.get("uri"):
                        rect = fitz.Rect(link["from"])
                        link_text = page.get_text("text", clip=rect).strip()
                        if link_text:
                            hyperlinks.append({"text": link_text, "uri": link["uri"]})

            pdf_doc.close()
        except ImportError:
            pass

        sessions[session_id]["image_positions"] = image_positions
        sessions[session_id]["hyperlinks"] = hyperlinks
        sessions[session_id]["image_source"] = "pdf"

    elif draft_path_lower.endswith(".docx"):
        import zipfile
        image_positions = []
        hyperlinks = []
        try:
            with zipfile.ZipFile(draft_path, 'r') as z:
                xml = z.read('word/document.xml').decode('utf-8')
                rid_to_file = {}
                rid_to_hyperlink = {}
                try:
                    rels_xml = z.read('word/_rels/document.xml.rels').decode('utf-8')
                    for rm in re.finditer(r'Id="(rId\d+)"[^>]*Target="media/([^"]+)"', rels_xml):
                        rid_to_file[rm.group(1)] = rm.group(2)
                    for rm in re.finditer(r'Id="(rId\d+)"[^>]*Type="[^"]*hyperlink[^"]*"[^>]*Target="([^"]+)"', rels_xml):
                        rid_to_hyperlink[rm.group(1)] = rm.group(2)
                except KeyError:
                    pass

                # Extract hyperlinks
                for hm in re.finditer(r'<w:hyperlink[^>]*>(.*?)</w:hyperlink>', xml, re.DOTALL):
                    full_tag = hm.group(0)
                    inner = hm.group(1)
                    texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', inner)
                    link_text = ''.join(texts).strip()
                    rid_m = re.search(r'r:id="(rId\d+)"', full_tag)
                    if rid_m and rid_m.group(1) in rid_to_hyperlink:
                        hyperlinks.append({"text": link_text, "uri": rid_to_hyperlink[rid_m.group(1)]})

                # Extract image files
                for img_filename in rid_to_file.values():
                    img_zip_path = f"word/media/{img_filename}"
                    if img_zip_path in z.namelist():
                        (images_dir / img_filename).write_bytes(z.read(img_zip_path))

                # Track image positions in document
                numbered_para_idx = 0
                for m_para in re.finditer(r'<w:p [^>]*>(.*?)</w:p>', xml, re.DOTALL):
                    para = m_para.group(1)
                    has_drawing = '<w:drawing' in para
                    texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', para)
                    text = ''.join(texts).strip()

                    if has_drawing:
                        blip_m = re.search(r'<a:blip[^>]*r:embed="(rId\d+)"', para)
                        extent_m = re.search(r'<wp:extent\\s+cx="(\\d+)"\\s+cy="(\\d+)"', para)
                        if blip_m and blip_m.group(1) in rid_to_file:
                            img_file = rid_to_file[blip_m.group(1)]
                            w_emu = int(extent_m.group(1)) if extent_m else 4572000
                            h_emu = int(extent_m.group(2)) if extent_m else 3429000
                            image_positions.append({
                                "src": img_file,
                                "width_emu": w_emu,
                                "height_emu": h_emu,
                                "after_numbered_idx": numbered_para_idx - 1,
                            })

                    if text:
                        ilvl_m = re.search(r'w:ilvl w:val="(\\d+)"', para)
                        if ilvl_m:
                            numbered_para_idx += 1
        except Exception:
            pass

        sessions[session_id]["image_positions"] = image_positions
        sessions[session_id]["hyperlinks"] = hyperlinks
        sessions[session_id]["image_source"] = "docx"


@app.route("/api/upload", methods=["POST"])
def upload():
    """Upload template and/or draft files. Returns a session ID."""
    session_id = request.form.get("session_id") or str(uuid.uuid4())

    if session_id not in sessions:
        sessions[session_id] = {"template": None, "draft": None}

    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(exist_ok=True)

    for field in ["template", "draft"]:
        if field in request.files:
            f = request.files[field]
            ext = os.path.splitext(f.filename)[1].lower() if f.filename else ".docx"
            if ext not in (".docx", ".pdf"):
                ext = ".docx"
            path = session_dir / f"{field}{ext}"
            f.save(str(path))
            sessions[session_id][field] = str(path)

            # Extract images and hyperlinks at upload time so they're available
            # for both the API extract and external LLM paste flows
            if field == "draft":
                _extract_draft_assets(session_id, str(path))

    return jsonify({
        "session_id": session_id,
        "template": sessions[session_id]["template"] is not None,
        "draft": sessions[session_id]["draft"] is not None,
    })


@app.route("/api/extract", methods=["POST"])
def extract():
    """Phase 0: Load the tested Phase 0 prompt, send draft to LLM, get full config back."""
    data = request.json
    session_id = data.get("session_id")

    if not session_id or session_id not in sessions:
        return jsonify({"error": "Invalid session"}), 400

    draft_path = sessions[session_id].get("draft")
    if not draft_path or not os.path.exists(draft_path):
        return jsonify({"error": "No draft uploaded"}), 400

    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY not set in environment"}), 500

    # ============================================================
    # STEP 1: Load Phase 0 prompt from file
    # ============================================================
    prompt_path = PIPELINE_DIR / "JENNY_Phase0_Extraction_Prompt.md"
    if not prompt_path.exists():
        return jsonify({"error": f"Phase 0 prompt not found: {prompt_path}"}), 500

    prompt_content = prompt_path.read_text(encoding="utf-8")
    # Parse the two code blocks: system message and user message
    blocks = re.findall(r'```\n(.*?)```', prompt_content, re.DOTALL)
    if len(blocks) < 2:
        return jsonify({"error": "Could not parse Phase 0 prompt (expected 2 code blocks)"}), 500

    system_msg = blocks[0].strip()
    user_msg_template = blocks[1].strip()

    # ============================================================
    # STEP 2: Extract structured text from draft (.docx or .pdf)
    # .docx: Include [ilvl=N] markers and [highlight=color] from XML
    # .pdf: Extract plain text (no structural metadata available)
    # ============================================================
    try:
        if draft_path.lower().endswith(".pdf"):
            import subprocess
            try:
                r = subprocess.run(
                    ["pdftotext", "-layout", draft_path, "-"],
                    capture_output=True, text=True, timeout=30
                )
                if r.returncode == 0 and r.stdout.strip():
                    draft_text = r.stdout.strip()
                else:
                    raise FileNotFoundError("pdftotext not available")
            except (FileNotFoundError, OSError):
                try:
                    from pdfminer.high_level import extract_text
                    draft_text = extract_text(draft_path).strip()
                except ImportError:
                    try:
                        import PyPDF2
                        reader = PyPDF2.PdfReader(draft_path)
                        pages = [p.extract_text() or "" for p in reader.pages]
                        draft_text = "\n".join(pages).strip()
                    except ImportError:
                        return jsonify({
                            "error": "PDF support requires pdftotext (poppler), pdfminer.six, or PyPDF2. Install one: pip install pdfminer.six"
                        }), 500

            if not draft_text:
                return jsonify({"error": "Could not extract text from PDF. File may be scanned/image-only."}), 400

            # Images and hyperlinks already extracted at upload time by _extract_draft_assets
            # No need to re-extract here

        else:
            import zipfile
            with zipfile.ZipFile(draft_path, 'r') as z:
                xml = z.read('word/document.xml').decode('utf-8')

                # --- HYPERLINK + IMAGE EXTRACTION ---
                # Build rId mappings from rels
                rid_to_file = {}
                rid_to_hyperlink = {}
                try:
                    rels_xml = z.read('word/_rels/document.xml.rels').decode('utf-8')
                    for rm in re.finditer(r'Id="(rId\d+)"[^>]*Target="media/([^"]+)"', rels_xml):
                        rid_to_file[rm.group(1)] = rm.group(2)
                    for rm in re.finditer(r'Id="(rId\d+)"[^>]*Type="[^"]*hyperlink[^"]*"[^>]*Target="([^"]+)"', rels_xml):
                        rid_to_hyperlink[rm.group(1)] = rm.group(2)
                except KeyError:
                    pass  # No rels file

                # Extract hyperlinks from document.xml
                docx_hyperlinks = []
                for hm in re.finditer(r'<w:hyperlink[^>]*>(.*?)</w:hyperlink>', xml, re.DOTALL):
                    full_tag = hm.group(0)
                    inner = hm.group(1)
                    texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', inner)
                    link_text = ''.join(texts).strip()
                    # External hyperlink via r:id
                    rid_m = re.search(r'r:id="(rId\d+)"', full_tag)
                    if rid_m and rid_m.group(1) in rid_to_hyperlink:
                        docx_hyperlinks.append({
                            "text": link_text,
                            "uri": rid_to_hyperlink[rid_m.group(1)],
                        })

                # Extract image files to session images directory
                session_dir = UPLOAD_DIR / session_id
                images_dir = session_dir / "images"
                images_dir.mkdir(exist_ok=True)
                for img_filename in rid_to_file.values():
                    img_zip_path = f"word/media/{img_filename}"
                    if img_zip_path in z.namelist():
                        (images_dir / img_filename).write_bytes(z.read(img_zip_path))

            # Parse paragraphs: extract text AND track image positions
            structured_lines = []
            image_positions = []  # {"src", "width_emu", "height_emu", "after_text_idx"}
            text_para_idx = 0  # counts only text paragraphs (what LLM sees)
            numbered_para_idx = 0  # counts only numbered (ilvl) paragraphs = S6 region

            for m_para in re.finditer(r'<w:p [^>]*>(.*?)</w:p>', xml, re.DOTALL):
                para = m_para.group(1)
                has_drawing = '<w:drawing' in para
                texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', para)
                text = ''.join(texts).strip()

                # Track images (even if paragraph also has text)
                if has_drawing:
                    blip_m = re.search(r'<a:blip[^>]*r:embed="(rId\d+)"', para)
                    extent_m = re.search(r'<wp:extent\s+cx="(\d+)"\s+cy="(\d+)"', para)
                    if blip_m and blip_m.group(1) in rid_to_file:
                        img_file = rid_to_file[blip_m.group(1)]
                        w_emu = int(extent_m.group(1)) if extent_m else 4572000
                        h_emu = int(extent_m.group(2)) if extent_m else 3429000
                        image_positions.append({
                            "src": img_file,
                            "width_emu": w_emu,
                            "height_emu": h_emu,
                            "after_numbered_idx": numbered_para_idx - 1,
                        })

                if not text:
                    continue

                ilvl_m = re.search(r'w:ilvl w:val="(\d+)"', para)
                hl_vals = re.findall(r'w:highlight w:val="([^"]+)"', para)
                hl_color = hl_vals[0] if hl_vals else None

                if ilvl_m:
                    ilvl = ilvl_m.group(1)
                    numbered_para_idx += 1
                    if hl_color:
                        structured_lines.append(f'[ilvl={ilvl}, highlight={hl_color}] {text}')
                    else:
                        structured_lines.append(f'[ilvl={ilvl}] {text}')
                else:
                    if hl_color:
                        structured_lines.append(f'[highlight={hl_color}] {text}')
                    else:
                        structured_lines.append(text)

                text_para_idx += 1

            draft_text = "\n".join(structured_lines)

            # Store image positions and hyperlinks if not already extracted at upload
            if not sessions[session_id].get("image_positions"):
                sessions[session_id]["image_positions"] = image_positions
            if not sessions[session_id].get("hyperlinks"):
                sessions[session_id]["hyperlinks"] = docx_hyperlinks

    except Exception as e:
        return jsonify({"error": f"Failed to read draft: {e}"}), 500

    # ============================================================
    # STEP 3: Build the user message with draft text appended
    # Inject image markers so LLM knows images exist in the source
    # ============================================================
    image_positions = sessions[session_id].get("image_positions", [])
    if image_positions:
        lines = draft_text.split("\n")
        image_source = sessions[session_id].get("image_source", "docx")
        if image_source == "pdf":
            # Insert markers proportionally through the text
            for img in sorted(image_positions, key=lambda x: x["position_frac"], reverse=True):
                insert_line = min(int(img["position_frac"] * len(lines)), len(lines))
                lines.insert(insert_line, f'[IMAGE: {img["src"]}]')
        else:
            # .docx: insert after numbered paragraph index
            offset = 0
            for img in sorted(image_positions, key=lambda x: x.get("after_numbered_idx", 0)):
                insert_line = min(img.get("after_numbered_idx", 0) + 1 + offset, len(lines))
                lines.insert(insert_line, f'[IMAGE: {img["src"]}]')
                offset += 1
        draft_text = "\n".join(lines)

    user_msg = user_msg_template + "\n\n--- SOURCE DRAFT CONTENT ---\n\n" + draft_text[:15000]

    # ============================================================
    # STEP 4: Call LLM API
    # ============================================================
    model_used = "claude-sonnet-4-6"

    payload = json.dumps({
        "model": model_used,
        "max_tokens": 8000,
        "system": system_msg,
        "messages": [{"role": "user", "content": user_msg}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        return jsonify({"error": f"Anthropic API error {e.code}: {body[:300]}"}), 502
    except Exception as e:
        return jsonify({"error": f"API call failed: {e}"}), 502

    # ============================================================
    # STEP 5: Parse the Python config response
    # The Phase 0 prompt returns a Python file, not JSON.
    # Extract the JENNY_CONFIG dict from it.
    # ============================================================
    raw_text = "".join(b.get("text", "") for b in resp_data.get("content", []))

    try:
        config = parse_config_safely(raw_text)
        if not config:
            return jsonify({
                "error": "No JENNY_CONFIG found in LLM response",
                "raw_response": raw_text[:2000],
            }), 422
    except Exception as e:
        return jsonify({
            "error": f"Failed to parse config: {e}",
            "raw_response": raw_text[:2000],
        }), 422

    # ============================================================
    # STEP 6: Set author from model used
    # ============================================================
    model_label = model_used.replace("claude-", "").replace("-", " ").title()
    config["author"] = f"JENNY {model_label}"

    # ============================================================
    # STEP 7: Sanitize
    # ============================================================
    config, issues = sanitize_config(config)

    # ============================================================
    # STEP 7b: Splice extracted images into s6_steps
    # .docx images: positioned by after_numbered_idx (paragraph-level)
    # PDF images: positioned by position_frac (page-level proportion)
    # ============================================================
    image_positions = sessions[session_id].get("image_positions", [])
    if image_positions and "s6_steps" in config:
        image_source = sessions[session_id].get("image_source", "docx")

        def make_image_entry(img, parent_ilvl=0):
            return {
                "type": "image",
                "src": img["src"],
                "ilvl": parent_ilvl,
                "width_emu": img["width_emu"],
                "height_emu": img["height_emu"],
            }

        if image_source == "pdf":
            # PDF: position images after the step they follow in the source
            num_steps = len(config["s6_steps"])
            new_steps = []
            img_at_step = {}
            for img in image_positions:
                if "after_step_idx" in img:
                    target_idx = min(img["after_step_idx"], num_steps - 1)
                else:
                    # Fallback to proportional if no step mapping
                    target_idx = int(img["position_frac"] * num_steps)
                    target_idx = min(target_idx, num_steps - 1)
                img_at_step.setdefault(target_idx, []).append(img)

            for step_idx, step in enumerate(config["s6_steps"]):
                step["type"] = "text"
                new_steps.append(step)
                for img in img_at_step.get(step_idx, []):
                    new_steps.append(make_image_entry(img, step.get("ilvl", 0)))
        else:
            # .docx: position by after_numbered_idx
            new_steps = []
            for step_idx, step in enumerate(config["s6_steps"]):
                for img in image_positions:
                    if img["after_numbered_idx"] == step_idx - 1:
                        prev_ilvl = config["s6_steps"][step_idx - 1].get("ilvl", 0) if step_idx > 0 else 0
                        new_steps.append(make_image_entry(img, prev_ilvl))
                step["type"] = "text"
                new_steps.append(step)

            last_idx = len(config["s6_steps"]) - 1
            for img in image_positions:
                if img["after_numbered_idx"] >= last_idx:
                    last_ilvl = config["s6_steps"][-1].get("ilvl", 0) if config["s6_steps"] else 0
                    new_steps.append(make_image_entry(img, last_ilvl))

        config["s6_steps"] = new_steps

    # ============================================================
    # STEP 7c: Attach hyperlinks to matching steps
    # ============================================================
    hyperlinks = sessions[session_id].get("hyperlinks", [])
    if hyperlinks and "s6_steps" in config:
        for step in config["s6_steps"]:
            if step.get("type", "text") != "text":
                continue
            step_links = []
            step_text = step.get("text", "")
            for hl in hyperlinks:
                if hl["text"] and hl["text"] in step_text:
                    step_links.append({"text": hl["text"], "uri": hl["uri"]})
            if step_links:
                step["hyperlinks"] = step_links

    # ============================================================
    # STEP 8: Return config + stats
    # ============================================================
    steps = config.get("s6_steps", [])
    text_steps = [s for s in steps if s.get("type", "text") == "text"]
    image_steps = [s for s in steps if s.get("type") == "image"]
    stats = {
        "total_steps": len(text_steps),
        "total_images": len(image_steps),
        "ilvl0": sum(1 for s in text_steps if s.get("ilvl") == 0),
        "ilvl1": sum(1 for s in text_steps if s.get("ilvl") == 1),
        "ilvl2": sum(1 for s in text_steps if s.get("ilvl") == 2),
        "ilvl3": sum(1 for s in text_steps if s.get("ilvl") == 3),
        "highlighted": sum(1 for s in text_steps if s.get("highlighted")),
        "roles": len(config.get("s4_roles", [])),
        "guidelines": len(config.get("s7_guidelines", [])),
    }

    return jsonify({
        "config": config,
        "issues": issues,
        "stats": stats,
        "draft_chars": len(draft_text),
        "model": model_used,
    })


@app.route("/api/sanitize", methods=["POST"])
def sanitize():
    """Sanitize an LLM-generated config before pipeline execution."""
    data = request.json
    config = data.get("config")
    if not config:
        return jsonify({"error": "No config provided"}), 400

    sanitized, issues = sanitize_config(config)

    # Compute stats (filter image entries from text-specific counts)
    steps = sanitized.get("s6_steps", [])
    text_steps = [s for s in steps if s.get("type", "text") == "text"]
    image_steps = [s for s in steps if s.get("type") == "image"]
    stats = {
        "total_steps": len(text_steps),
        "total_images": len(image_steps),
        "ilvl0": sum(1 for s in text_steps if s.get("ilvl") == 0),
        "ilvl1": sum(1 for s in text_steps if s.get("ilvl") == 1),
        "ilvl2": sum(1 for s in text_steps if s.get("ilvl") == 2),
        "ilvl3": sum(1 for s in text_steps if s.get("ilvl") == 3),
        "highlighted": sum(1 for s in text_steps if s.get("highlighted")),
        "roles": len(sanitized.get("s4_roles", [])),
        "guidelines": len(sanitized.get("s7_guidelines", [])),
    }

    return jsonify({
        "config": config,
        "issues": issues,
        "stats": stats,
    })


@app.route("/api/get-prompt", methods=["POST"])
def get_prompt():
    """Return the extraction prompt with the user's draft text pre-assembled.
    Users copy this into an external LLM (ChatGPT, Gemini, etc.)."""
    data = request.json
    session_id = data.get("session_id")

    if not session_id or session_id not in sessions:
        return jsonify({"error": "Upload files first"}), 400

    draft_path = sessions[session_id].get("draft")
    if not draft_path or not os.path.exists(draft_path):
        return jsonify({"error": "No draft uploaded"}), 400

    # Load prompt
    prompt_path = PIPELINE_DIR / "JENNY_Phase0_Extraction_Prompt.md"
    if not prompt_path.exists():
        return jsonify({"error": "Prompt file not found"}), 500

    prompt_content = prompt_path.read_text(encoding="utf-8")
    blocks = re.findall(r'```\n(.*?)```', prompt_content, re.DOTALL)
    if len(blocks) < 2:
        return jsonify({"error": "Could not parse prompt"}), 500

    system_msg = blocks[0].strip()
    user_msg_template = blocks[1].strip()

    # Extract draft text and images
    image_positions = sessions[session_id].get("image_positions", [])
    try:
        if draft_path.lower().endswith(".pdf"):
            import fitz
            pdf = fitz.open(draft_path)
            draft_text = "\n".join(page.get_text() for page in pdf)
            # Extract images if not already done
            if not image_positions:
                img_dir = UPLOAD_DIR / session_id / "images"
                img_dir.mkdir(parents=True, exist_ok=True)
                total_pages = len(pdf)
                img_idx = 0
                for page_num, page in enumerate(pdf):
                    for img_info in page.get_images(full=True):
                        xref = img_info[0]
                        pix = fitz.Pixmap(pdf, xref)
                        if pix.n > 4:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        fname = f"pdf_image_{img_idx}.png"
                        pix.save(str(img_dir / fname))
                        image_positions.append({
                            "src": fname,
                            "width_emu": pix.width * 9525,
                            "height_emu": pix.height * 9525,
                            "position_frac": (page_num + 0.5) / max(total_pages, 1),
                        })
                        img_idx += 1
                sessions[session_id]["image_positions"] = image_positions
                sessions[session_id]["image_source"] = "pdf"
            pdf.close()
        else:
            import zipfile
            with zipfile.ZipFile(draft_path, 'r') as z:
                xml = z.read('word/document.xml').decode('utf-8')
            draft_text = re.sub(r'<[^>]+>', ' ', xml)
            draft_text = re.sub(r'\s+', ' ', draft_text).strip()
    except Exception as e:
        return jsonify({"error": f"Could not read draft: {e}"}), 500

    # Inject image markers
    if image_positions:
        lines = draft_text.split("\n")
        for img in sorted(image_positions, key=lambda x: x.get("position_frac", 0), reverse=True):
            insert_line = int(img.get("position_frac", 0) * len(lines))
            lines.insert(insert_line, f'[IMAGE: {img["src"]}]')
        draft_text = "\n".join(lines)

    # Assemble the full prompt
    full_prompt = f"{system_msg}\n\n---\n\n{user_msg_template}\n\n---\n\nSOURCE DOCUMENT:\n\n{draft_text}"

    return jsonify({"prompt": full_prompt})


@app.route("/api/import-config", methods=["POST"])
def import_config():
    """Import a config from external source (Plan B/C).
    Accepts raw text: Python file with JENNY_CONFIG dict, or JSON.
    Parses, sanitizes, and returns the config ready for review."""
    data = request.json
    raw = data.get("raw_config", "").strip()

    if not raw:
        return jsonify({"error": "No config text provided"}), 400

    config = None
    source = "imported"

    # Clean common chatbot artifacts before parsing
    # Remove stray "Copy" text from copy-button UI artifacts
    raw = re.sub(r'\n\s*Copy\n', '\n', raw)
    raw = re.sub(r',\s*Copy\s*"', ', "', raw)
    # Remove "Copy code" buttons
    raw = re.sub(r'\n\s*Copy code\n', '\n', raw)
    # Strip leading/trailing prose before/after the config
    # Find the actual config start
    config_start = raw.find("JENNY_CONFIG")
    if config_start > 0:
        raw = raw[config_start:]
    # Strip markdown fences
    if raw.strip().startswith("```"):
        raw = re.sub(r'^```\w*\n', '', raw.strip())
        raw = re.sub(r'\n```\s*$', '', raw)

    # Try 1: Parse as Python dict literal (JENNY_CONFIG = {...})
    if "JENNY_CONFIG" in raw:
        try:
            config = parse_config_safely(raw)
            source = "python-import"
        except Exception:
            pass

    # Try 2: Parse as JSON
    if not config:
        try:
            config = json.loads(raw)
            source = "json-import"
        except json.JSONDecodeError:
            pass

    # Try 3: Find a JSON object in the text
    if not config:
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            try:
                config = json.loads(m.group())
                source = "json-extract"
            except json.JSONDecodeError:
                pass

    if not config:
        return jsonify({
            "error": "Could not parse config. Expected a Python file with JENNY_CONFIG = {...} or a JSON object.",
        }), 422

    # Validate it has the minimum required fields
    if "s6_steps" not in config:
        return jsonify({"error": "Config missing s6_steps field"}), 422

    # Sanitize
    config, issues = sanitize_config(config)

    # Splice images and hyperlinks from session (same as /api/extract Step 7b/7c)
    session_id = data.get("session_id")
    if session_id and session_id in sessions:
        # Image splice
        image_positions = sessions[session_id].get("image_positions", [])
        if image_positions and "s6_steps" in config:
            image_source = sessions[session_id].get("image_source", "docx")

            def make_image_entry(img, parent_ilvl=0):
                return {
                    "type": "image",
                    "src": img["src"],
                    "ilvl": parent_ilvl,
                    "width_emu": img["width_emu"],
                    "height_emu": img["height_emu"],
                }

            if image_source == "pdf":
                num_steps = len(config["s6_steps"])
                new_steps = []
                img_at_step = {}
                for img in image_positions:
                    if "after_step_idx" in img:
                        target_idx = min(img["after_step_idx"], num_steps - 1)
                    else:
                        target_idx = int(img["position_frac"] * num_steps)
                        target_idx = min(target_idx, num_steps - 1)
                    img_at_step.setdefault(target_idx, []).append(img)
                for step_idx, step in enumerate(config["s6_steps"]):
                    step["type"] = "text"
                    new_steps.append(step)
                    for img in img_at_step.get(step_idx, []):
                        new_steps.append(make_image_entry(img, step.get("ilvl", 0)))
            else:
                new_steps = []
                for step_idx, step in enumerate(config["s6_steps"]):
                    for img in image_positions:
                        if img["after_numbered_idx"] == step_idx - 1:
                            prev_ilvl = config["s6_steps"][step_idx - 1].get("ilvl", 0) if step_idx > 0 else 0
                            new_steps.append(make_image_entry(img, prev_ilvl))
                    step["type"] = "text"
                    new_steps.append(step)
                last_idx = len(config["s6_steps"]) - 1
                for img in image_positions:
                    if img["after_numbered_idx"] >= last_idx:
                        last_ilvl = config["s6_steps"][-1].get("ilvl", 0) if config["s6_steps"] else 0
                        new_steps.append(make_image_entry(img, last_ilvl))

            config["s6_steps"] = new_steps

        # Hyperlink attach
        hyperlinks = sessions[session_id].get("hyperlinks", [])
        if hyperlinks and "s6_steps" in config:
            for step in config["s6_steps"]:
                if step.get("type", "text") != "text":
                    continue
                step_links = []
                step_text = step.get("text", "")
                for hl in hyperlinks:
                    if hl["text"] and hl["text"] in step_text:
                        step_links.append({"text": hl["text"], "uri": hl["uri"]})
                if step_links:
                    step["hyperlinks"] = step_links

    # Stats (filter image entries from text-specific counts)
    steps = config.get("s6_steps", [])
    text_steps = [s for s in steps if s.get("type", "text") == "text"]
    image_steps = [s for s in steps if s.get("type") == "image"]
    stats = {
        "total_steps": len(text_steps),
        "total_images": len(image_steps),
        "ilvl0": sum(1 for s in text_steps if s.get("ilvl") == 0),
        "ilvl1": sum(1 for s in text_steps if s.get("ilvl") == 1),
        "ilvl2": sum(1 for s in text_steps if s.get("ilvl") == 2),
        "ilvl3": sum(1 for s in text_steps if s.get("ilvl") == 3),
        "highlighted": sum(1 for s in text_steps if s.get("highlighted")),
        "roles": len(config.get("s4_roles", [])),
        "guidelines": len(config.get("s7_guidelines", [])),
    }

    return jsonify({
        "config": config,
        "issues": issues,
        "stats": stats,
        "source": source,
    })


@app.route("/api/generate", methods=["POST"])
def generate():
    """Run the JENNY pipeline with a validated config. Returns the .docx."""
    data = request.json
    session_id = data.get("session_id")
    config = data.get("config")

    if not session_id or session_id not in sessions:
        return jsonify({"error": "Invalid session"}), 400
    if not config:
        return jsonify({"error": "No config provided"}), 400

    template_path = sessions[session_id].get("template")
    if not template_path or not os.path.exists(template_path):
        return jsonify({"error": "No template uploaded"}), 400

    # Create job directory
    job_id = str(uuid.uuid4())[:8]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    try:
        result = run_jenny_pipeline(config, template_path, None, job_dir, session_id=session_id)

        if result["success"]:
            # Parse score from stdout
            score_match = re.search(r"SCORE:\s*(\d+)/(\d+)\s*\((\d+)%\)", result["stdout"])
            score = score_match.group(0) if score_match else "Unknown"

            return jsonify({
                "success": True,
                "job_id": job_id,
                "score": score,
                "log": result["stdout"],
                "download_url": f"/api/download/{job_id}",
            })
        else:
            return jsonify({
                "success": False,
                "log": result["stdout"],
                "error": result["stderr"],
            }), 500

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Pipeline timed out (120s)"}), 504
    except Exception as e:
        print(f"Pipeline error: {traceback.format_exc()}")  # Log server-side only
        return jsonify({"error": "Pipeline execution failed"}), 500


@app.route("/api/download/<job_id>", methods=["GET"])
def download(job_id):
    """Download the generated .docx file."""
    output_path = JOBS_DIR / job_id / "OUTPUT.docx"
    if not output_path.exists():
        return jsonify({"error": "File not found"}), 404

    return send_file(
        str(output_path),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=f"SOP_JENNY_{job_id}.docx",
    )


@app.route("/api/image/<session_id>/<filename>", methods=["GET"])
def serve_image(session_id, filename):
    """Serve an extracted image from the session's images directory."""
    safe_name = os.path.basename(filename)
    image_path = UPLOAD_DIR / session_id / "images" / safe_name
    if not image_path.exists():
        return jsonify({"error": "Image not found"}), 404

    ext = safe_name.rsplit(".", 1)[-1].lower()
    mime = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg",
            "gif": "image/gif", "bmp": "image/bmp"}.get(ext, "application/octet-stream")

    return send_file(str(image_path), mimetype=mime)


# ============================================================
# API KEY MANAGEMENT
# ============================================================

@app.route("/api/key-status", methods=["GET"])
def key_status():
    return jsonify({
        "has_key": bool(ANTHROPIC_API_KEY),
        "keyed_build": EMBEDDED_API_KEY is not None,
    })

@app.route("/api/set-key", methods=["POST"])
def set_key():
    global ANTHROPIC_API_KEY
    key = request.json.get("key", "").strip()
    if not key.startswith("sk-ant-"):
        return jsonify({"error": "Invalid key format — must start with sk-ant-"}), 400
    ANTHROPIC_API_KEY = key
    return jsonify({"status": "ok"})


# ============================================================
# FRONTEND SERVING (production / exe mode)
# ============================================================

# Detect PyInstaller bundle
if getattr(sys, '_MEIPASS', None):
    FRONTEND_DIR = Path(sys._MEIPASS) / "frontend_dist"
else:
    FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    if path.startswith("api/"):
        return jsonify({"error": "Not found"}), 404
    file_path = FRONTEND_DIR / path
    if file_path.is_file():
        return send_file(str(file_path))
    index = FRONTEND_DIR / "index.html"
    if index.is_file():
        return send_file(str(index))
    return jsonify({"error": "Frontend not built. Run: cd frontend && npm run build"}), 404


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import webbrowser
    print("JENNY SOP Generator Backend")
    print(f"  Pipeline dir: {PIPELINE_DIR}")
    print(f"  Upload dir:   {UPLOAD_DIR}")
    print(f"  Jobs dir:     {JOBS_DIR}")
    print()
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    host = "127.0.0.1"
    port = 5000
    # Auto-open browser when running as bundled exe
    if getattr(sys, '_MEIPASS', None):
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()
        print(f"  Opening browser at http://localhost:{port}")
    if debug:
        app.run(host=host, port=port, debug=True)
    else:
        from waitress import serve
        print(f" * Serving on http://{host}:{port}")
        serve(app, host=host, port=port, threads=4)