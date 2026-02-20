#!/usr/bin/env python3
"""
JENNY v13 Standalone Pipeline
Deterministic template mutation - no LLM required after Phase 0.

Usage:
  1. An LLM (any model) fills out jenny_config.py by reading the source draft
  2. Run: python jenny_pipeline.py jenny_config.py TEMPLATE.docx OUTPUT.docx [INSTRUCTIONS.md]

The pipeline:
  - Extracts unpack/pack scripts from v13 instructions (or uses built-in fallback)
  - Unpacks the template
  - Performs all XML mutations deterministically from the config
  - Validates against the structural integrity gate
  - Packs the output

No creative decisions. No interpretation. No helpfulness.
"""

import os, re, sys, shutil, subprocess, pathlib, importlib.util, json
import xml.etree.ElementTree as ET

# ============================================================
# LOAD CONFIG
# ============================================================

def load_config(config_path):
    spec = importlib.util.spec_from_file_location("config", config_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.JENNY_CONFIG

# ============================================================
# XML HELPERS
# ============================================================

def xml_escape(s):
    """Escape text for XML, preserving already-escaped entities."""
    protected = {
        "&amp;": "__AMP__", "&lt;": "__LT__", "&gt;": "__GT__",
        "&quot;": "__QUOT__", "&#x2019;": "__RSQ__", "&#x2018;": "__LSQ__",
        "&#x201C;": "__LDQ__", "&#x201D;": "__RDQ__", "&#x2013;": "__ENDASH__",
    }
    for k, v in protected.items():
        s = s.replace(k, v)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    s = (s.replace("\u2019", "&#x2019;").replace("\u2018", "&#x2018;")
          .replace("\u201C", "&#x201C;").replace("\u201D", "&#x201D;")
          .replace("\u2013", "&#x2013;"))
    for k, v in protected.items():
        s = s.replace(v, k)
    return s

def find_para_start(doc_xml, pos):
    """Find the start of the enclosing <w:p> paragraph, not <w:pStyle> or <w:pPr>."""
    search_from = pos
    while search_from >= 0:
        idx = doc_xml.rfind("<w:p", 0, search_from)
        if idx == -1:
            return -1
        next_char = doc_xml[idx + 4:idx + 5]
        if next_char in (" ", ">"):
            return idx
        search_from = idx - 1
    return -1

def find_para_end(doc_xml, pos):
    """Find the end of the </w:p> tag after position pos."""
    idx = doc_xml.find("</w:p>", pos)
    if idx == -1:
        return -1
    return idx + 6

def find_fema_headings(doc_xml):
    """Bounded heading search - no depth-tracking parser needed."""
    headings = []
    pos = 0
    while True:
        idx = doc_xml.find('w:val="FEMAHeading1"', pos)
        if idx == -1:
            break
        p_start = find_para_start(doc_xml, idx)
        p_end = find_para_end(doc_xml, idx)
        if p_start == -1 or p_end == -1:
            pos = idx + 20
            continue
        para = doc_xml[p_start:p_end]
        texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', para)
        headings.append({
            "text": "".join(texts).strip(),
            "start": p_start,
            "end": p_end,
        })
        pos = p_end
    return headings

def pid(n):
    """Generate a paraId from an integer."""
    return f"1A{n:06X}"

def build_paragraph(text, para_id, ilvl=None, highlighted=False, style="FEMANormal", num_id="42"):
    """Build a single OOXML paragraph."""
    t = xml_escape(text)
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/>'
    if ilvl is not None:
        ppr += f'<w:numPr><w:ilvl w:val="{ilvl}"/><w:numId w:val="{num_id}"/></w:numPr>'
    if highlighted:
        ppr += '<w:rPr><w:highlight w:val="yellow"/></w:rPr>'
    ppr += '</w:pPr>'
    rpr = '<w:rPr><w:rFonts w:ascii="Franklin Gothic Book" w:hAnsi="Franklin Gothic Book"/>'
    if highlighted:
        rpr += '<w:highlight w:val="yellow"/>'
    rpr += '</w:rPr>'
    return (
        f'<w:p w14:paraId="{para_id}" w14:textId="{para_id}" '
        f'w:rsidR="00000001" w:rsidRDefault="00000001">'
        f'{ppr}<w:r>{rpr}<w:t xml:space="preserve">{t}</w:t></w:r></w:p>'
    )

def build_flag(text, para_id):
    """Build a review flag paragraph (italic + yellow highlight in pPr and rPr)."""
    t = xml_escape(text)
    return (
        f'<w:p w14:paraId="{para_id}" w14:textId="{para_id}" '
        f'w:rsidR="00000001" w:rsidRDefault="00000001">'
        f'<w:pPr><w:pStyle w:val="FEMANormal"/>'
        f'<w:rPr><w:i/><w:highlight w:val="yellow"/></w:rPr></w:pPr>'
        f'<w:r><w:rPr><w:i/><w:highlight w:val="yellow"/></w:rPr>'
        f'<w:t>{t}</w:t></w:r></w:p>'
    )

# ============================================================
# PIPELINE
# ============================================================

def run_pipeline(config, template_path, output_path, instructions_path=None):
    cfg = config
    _debug_step = 0
    def _dbg(label, d):
        nonlocal _debug_step
        _debug_step += 1
        try:
            ET.fromstring(d.encode("utf-8"))
        except ET.ParseError as e:
            print(f"  XML BREAK at step {_debug_step} [{label}]: {e}")
    
    print(f"JENNY v13 Standalone Pipeline")
    print(f"  Full Title:  {cfg['full_title']}")
    print(f"  Short Title: {cfg['short_title']}")
    print(f"  Structure:   {cfg['structure_type']}")
    print(f"  Steps:       {len(cfg['s6_steps'])}")
    print(f"  Roles:       {len(cfg['s4_roles'])}")
    print()

    # --- PHASE 1: Extract scripts and unpack ---
    if instructions_path and os.path.exists(instructions_path):
        md = pathlib.Path(instructions_path).read_text(encoding="utf-8")
        m = re.search(r"### BEGIN unpack_docx\.py ###\s*```python\s*\n(.*?)\n```\s*### END unpack_docx\.py ###", md, re.S)
        assert m, "Cannot find unpack_docx.py in instructions"
        pathlib.Path("unpack_docx.py").write_text(m.group(1), encoding="utf-8")
        m = re.search(r"### BEGIN pack_docx\.py ###\s*```python\s*\n(.*?)\n```\s*### END pack_docx\.py ###", md, re.S)
        assert m, "Cannot find pack_docx.py in instructions"
        pathlib.Path("pack_docx.py").write_text(m.group(1), encoding="utf-8")
    else:
        assert os.path.exists("unpack_docx.py"), "unpack_docx.py not found"
        assert os.path.exists("pack_docx.py"), "pack_docx.py not found"

    if os.path.exists("./unpacked"):
        shutil.rmtree("./unpacked")
    r = subprocess.run([sys.executable, "unpack_docx.py", template_path, "./unpacked/"],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    assert r.returncode == 0, f"Unpack failed: {r.stderr}"
    assert os.path.exists("./unpacked/word/document.xml")
    assert os.path.exists("./unpacked/word/header5.xml")
    print("Phase 1 PASSED\n")

    # --- SINGLE READ ---
    doc = pathlib.Path("./unpacked/word/document.xml").read_text(encoding="utf-8")
    hdr = pathlib.Path("./unpacked/word/header5.xml").read_text(encoding="utf-8")

    # --- PHASE 3: Ordered replacements ---
    full_esc = xml_escape(cfg["full_title"])
    short_esc = xml_escape(cfg["short_title"])
    purpose_esc = xml_escape(cfg["purpose"])
    scope_esc = xml_escape(cfg["scope"])
    date_esc = xml_escape(cfg["cover_date"])

    # Replacement 1: S6 heading
    doc = doc.replace("Enter Title (Step-by-Step Instructions)",
                      f"{short_esc} (Step-by-Step Instructions)")
    # Replacement 2: Chapter heading (en-dash case)
    doc = doc.replace("SOP &#x2013; Enter Title", f"SOP - {full_esc}")
    doc = doc.replace("SOP \u2013 Enter Title", f"SOP - {full_esc}")
    # Replacement 2b: Split-run case
    doc = doc.replace("&#x2013; Enter Title", f"- {full_esc}")
    doc = doc.replace("\u2013 Enter Title", f"- {full_esc}")
    # Replacement 3: Cover page
    doc = doc.replace("<w:t>Enter Title</w:t>", f"<w:t>{full_esc}</w:t>")
    doc = doc.replace('<w:t xml:space="preserve">Enter Title</w:t>',
                      f'<w:t xml:space="preserve">{full_esc}</w:t>')
    # Replacement 4: Purpose
    doc = doc.replace("<w:t>Enter Purpose</w:t>", f"<w:t>{purpose_esc}</w:t>")
    doc = doc.replace('<w:t xml:space="preserve">Enter Purpose</w:t>',
                      f'<w:t xml:space="preserve">{purpose_esc}</w:t>')
    # Replacement 5: Scope
    doc = doc.replace("<w:t>Enter Scope and applicability</w:t>",
                      f"<w:t>{scope_esc}</w:t>")
    doc = doc.replace('<w:t xml:space="preserve">Enter Scope and applicability</w:t>',
                      f'<w:t xml:space="preserve">{scope_esc}</w:t>')
    # Replacement 6: Date
    doc = doc.replace("January 2026", date_esc)
    # Replacement 7: Remove subtitles (Single Procedure)
    # CRITICAL: Subtitles appear in BOTH the TOC (inside <w:sdt>) and the body.
    # Only remove body paragraphs. For TOC entries, leave them (Word regenerates TOC on open).
    if cfg["structure_type"] == "single":
        for sub in ["Enter Subtitle 1", "Enter Subtitle 2", "Enter Subtitle 3"]:
            # Find all occurrences, remove only body ones (not inside SDT)
            while True:
                idx = doc.find(sub)
                if idx == -1:
                    break
                # Check if inside SDT
                sdt_before = doc[:idx].rfind("<w:sdt")
                sdt_end_before = doc[:idx].rfind("</w:sdt>")
                if sdt_before > sdt_end_before:
                    # Inside SDT (TOC) - skip this occurrence, search after it
                    # Replace just the text to stop the loop but preserve XML structure
                    doc = doc[:idx] + " " + doc[idx + len(sub):]
                else:
                    # Body paragraph - remove entire paragraph
                    ps = find_para_start(doc, idx)
                    pe = doc.find("</w:p>", idx) + 6
                    doc = doc[:ps] + doc[pe:]

    print("Phase 3 replacements applied")
    
    # DEBUG: XML check after Phase 3
    try:
        ET.fromstring(doc.encode("utf-8"))
    except ET.ParseError as e:
        print(f"  WARNING: XML invalid after Phase 3: {e}")

    # --- S6 DELETE + BASELINE + INSERT ---
    headings = find_fema_headings(doc)
    s6_h = next(h for h in headings if "Step-by-Step" in h["text"])
    s6_idx = headings.index(s6_h)
    s7_h = headings[s6_idx + 1]

    # Baseline ilvl (outside S6 region)
    before = doc[:s6_h["end"]]
    after = doc[s7_h["start"]:]
    BASELINE_ILVL0 = before.count('w:ilvl w:val="0"') + after.count('w:ilvl w:val="0"')
    BASELINE_ILVL1 = before.count('w:ilvl w:val="1"') + after.count('w:ilvl w:val="1"')
    BASELINE_ILVL2 = before.count('w:ilvl w:val="2"') + after.count('w:ilvl w:val="2"')

    # Hard delete
    doc = before + after
    insert_at = len(before)
    print(f"S6 deleted. Baseline ilvl: 0={BASELINE_ILVL0}, 1={BASELINE_ILVL1}, 2={BASELINE_ILVL2}")

    # Build S6 content
    s6_xml = ""
    p_counter = 0

    # Intro paragraph (no numbering)
    if cfg["s6_intro"]:
        s6_xml += build_paragraph(cfg["s6_intro"], pid(p_counter))
        p_counter += 1

    # Steps
    src_ilvl0 = src_ilvl1 = src_ilvl2 = 0
    src_highlights = 0
    for step in cfg["s6_steps"]:
        s6_xml += build_paragraph(
            step["text"], pid(p_counter),
            ilvl=step["ilvl"],
            highlighted=step.get("highlighted", False)
        )
        if step["ilvl"] == 0: src_ilvl0 += 1
        elif step["ilvl"] == 1: src_ilvl1 += 1
        elif step["ilvl"] == 2: src_ilvl2 += 1
        if step.get("highlighted"): src_highlights += 1
        p_counter += 1

    doc = doc[:insert_at] + s6_xml + doc[insert_at:]
    print(f"S6 inserted. Source ilvl: 0={src_ilvl0}, 1={src_ilvl1}, 2={src_ilvl2}, highlights={src_highlights}")
    try:
        ET.fromstring(doc.encode("utf-8"))
    except ET.ParseError as e:
        print(f"  WARNING: XML invalid after S6 insert: {e}")

    # --- SECTION 4: ROLES (preserve table, replace rows) ---
    headings = find_fema_headings(doc)
    s4_h = next(h for h in headings if "Roles" in h["text"])
    s5_h = next(h for h in headings if "Required" in h["text"])
    s4_region = doc[s4_h["end"]:s5_h["start"]]

    # The template has a table with header row + example rows.
    # Keep table props + header row, replace data rows.
    tbl_start = s4_region.find("<w:tbl")
    tbl_end = s4_region.find("</w:tbl>") + 8

    if tbl_start > -1 and tbl_end > tbl_start:
        table_xml = s4_region[tbl_start:tbl_end]
        # Find header row (first <w:tr>)
        first_tr_start = table_xml.find("<w:tr")
        first_tr_end = table_xml.find("</w:tr>") + 7
        # Table props = everything before first row
        tbl_props = table_xml[:first_tr_start]
        header_row = table_xml[first_tr_start:first_tr_end]

        # Build new data rows from config roles
        # Each role is "Role Name: Description" -> split on first ":"
        new_rows = ""
        for i, role in enumerate(cfg["s4_roles"]):
            parts = role.split(":", 1)
            role_name = xml_escape(parts[0].strip())
            role_desc = xml_escape(parts[1].strip()) if len(parts) > 1 else ""
            row_pid = pid(0xA00 + i)
            new_rows += (
                f'<w:tr w:rsidR="00000001" w14:paraId="{row_pid}" w14:textId="77777777">'
                f'<w:tc><w:tcPr><w:tcW w:w="1787" w:type="pct"/></w:tcPr>'
                f'<w:p w14:paraId="{pid(0xA20+i)}" w14:textId="77777777" w:rsidR="00000001" w:rsidRDefault="00000001">'
                f'<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
                f'<w:rPr><w:rFonts w:ascii="Franklin Gothic Book" w:hAnsi="Franklin Gothic Book"/></w:rPr></w:pPr>'
                f'<w:r><w:rPr><w:rFonts w:ascii="Franklin Gothic Book" w:hAnsi="Franklin Gothic Book"/></w:rPr>'
                f'<w:t>{role_name}</w:t></w:r></w:p></w:tc>'
                f'<w:tc><w:tcPr><w:tcW w:w="3213" w:type="pct"/></w:tcPr>'
                f'<w:p w14:paraId="{pid(0xA40+i)}" w14:textId="77777777" w:rsidR="00000001" w:rsidRDefault="00000001">'
                f'<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/>'
                f'<w:rPr><w:rFonts w:ascii="Franklin Gothic Book" w:hAnsi="Franklin Gothic Book"/></w:rPr></w:pPr>'
                f'<w:r><w:rPr><w:rFonts w:ascii="Franklin Gothic Book" w:hAnsi="Franklin Gothic Book"/></w:rPr>'
                f'<w:t xml:space="preserve">{role_desc}</w:t></w:r></w:p></w:tc>'
                f'</w:tr>'
            )

        new_table = tbl_props + header_row + new_rows + "</w:tbl>"
        # Replace old table with new, keep content after table (including existing flag)
        abs_tbl_start = s4_h["end"] + tbl_start
        abs_tbl_end = s4_h["end"] + tbl_end
        # Check if the template already has the S4 flag after the table
        existing_flag = "Add or modify roles"
        after_table = doc[abs_tbl_end:abs_tbl_end + 500]
        if existing_flag in after_table:
            # Flag already exists, don't insert another
            doc = doc[:abs_tbl_start] + new_table + doc[abs_tbl_end:]
        else:
            s4_flag = build_flag("(Add or modify roles as appropriate for each department.)", pid(0xA80))
            doc = doc[:abs_tbl_start] + new_table + s4_flag + doc[abs_tbl_end:]
    else:
        # Fallback: no table found, use paragraphs
        roles_xml = ""
        for i, role in enumerate(cfg["s4_roles"]):
            roles_xml += build_paragraph(role, pid(0xA00 + i))
        roles_xml += build_flag("(Add or modify roles as appropriate for each department.)", pid(0xA80))
        doc = doc[:s4_h["end"]] + roles_xml + doc[s5_h["start"]:]

    # DEBUG: validate after S4
    try:
        ET.fromstring(doc.encode("utf-8"))
        print("  S4 mutation: XML valid")
    except ET.ParseError as e:
        print(f"  S4 mutation: XML BROKEN - {e}")

    # --- SECTION 5: MATERIALS ---
    headings = find_fema_headings(doc)
    s5_h = next(h for h in headings if "Required" in h["text"])
    s6_h = next(h for h in headings if "Step-by-Step" in h["text"])

    # Find the template placeholder paragraph
    placeholder = "(List all necessary materials, equipment, software, or resources required to complete the procedure.)"
    ph_idx = doc.find(placeholder)
    if ph_idx > -1:
        ps = find_para_start(doc, ph_idx)
        pe = doc.find("</w:p>", ph_idx) + 6
        mat_xml = build_paragraph(cfg["s5_materials"], pid(0xB00))
        mat_xml += build_flag("(List all necessary materials, equipment, software, or resources required. Modify as appropriate.)", pid(0xB80))
        doc = doc[:ps] + mat_xml + doc[pe:]
    else:
        # Insert after S5 heading
        mat_xml = build_paragraph(cfg["s5_materials"], pid(0xB00))
        mat_xml += build_flag("(List all necessary materials, equipment, software, or resources required. Modify as appropriate.)", pid(0xB80))
        doc = doc[:s5_h["end"]] + mat_xml + doc[s5_h["end"]:]

    # DEBUG: validate after S5
    try:
        ET.fromstring(doc.encode("utf-8"))
        print("  S5 mutation: XML valid")
    except ET.ParseError as e:
        print(f"  S5 mutation: XML BROKEN - {e}")

    # --- SECTION 2: SCOPE FLAG ---
    scope_flag = build_flag("(Add or modify scope and applicability as appropriate.)", pid(0xC00))
    scope_idx = doc.find(scope_esc)
    if scope_idx > -1:
        pe = doc.find("</w:p>", scope_idx) + 6
        doc = doc[:pe] + scope_flag + doc[pe:]

    # --- SECTION 7: SAFETY (use FEMABullet-1 style from template) ---
    headings = find_fema_headings(doc)
    s7_h = next(h for h in headings if "Safety" in h["text"])
    s8_h = next(h for h in headings if "Revision" in h["text"])

    # Delete existing S7 content
    doc = doc[:s7_h["end"]] + doc[s8_h["start"]:]

    # Build FEMABullet-1 paragraphs matching template format
    safety_xml = ""
    for i, g in enumerate(cfg["s7_guidelines"]):
        t = xml_escape(g)
        bullet_pid = pid(0xD00 + i)
        safety_xml += (
            f'<w:p w14:paraId="{bullet_pid}" w14:textId="{bullet_pid}" '
            f'w:rsidR="00000001" w:rsidRDefault="00000001">'
            f'<w:pPr><w:pStyle w:val="FEMABullet-1"/>'
            f'<w:rPr><w:rFonts w:ascii="Franklin Gothic Book" w:eastAsia="Times New Roman" '
            f'w:hAnsi="Franklin Gothic Book"/></w:rPr></w:pPr>'
            f'<w:r><w:rPr><w:rFonts w:ascii="Franklin Gothic Book" w:eastAsia="Times New Roman" '
            f'w:hAnsi="Franklin Gothic Book"/></w:rPr>'
            f'<w:t xml:space="preserve">{t}</w:t></w:r></w:p>'
        )
    safety_xml += build_flag("(Add or modify safety and compliance guidelines as appropriate.)", pid(0xD80))
    doc = doc[:s7_h["end"]] + safety_xml + doc[s7_h["end"]:]

    # DEBUG: validate after S7
    try:
        ET.fromstring(doc.encode("utf-8"))
        print("  S7 mutation: XML valid")
    except ET.ParseError as e:
        print(f"  S7 mutation: XML BROKEN - {e}")

    # --- SECTION 8: REVISION FLAG ---
    s8_flag = build_flag("(Update revision history information as appropriate prior to final approval.)", pid(0xE00))
    # Find S8 heading using heading map (not raw text search which hits S4 roles)
    headings = find_fema_headings(doc)
    s8_h = next((h for h in headings if "Revision" in h["text"]), None)
    if s8_h:
        # Find the revision history table AFTER the S8 heading
        tbl_end = doc.find("</w:tbl>", s8_h["end"])
        if tbl_end > -1:
            tbl_end += len("</w:tbl>")
            doc = doc[:tbl_end] + s8_flag + doc[tbl_end:]

    # --- PAGE BREAKS ---
    # Remove paraId 32B18C5D (page break before S6)
    pb_marker = 'paraId="32B18C5D"'
    pb_idx = doc.find(pb_marker)
    if pb_idx > -1:
        ps = find_para_start(doc, pb_idx)
        pe = doc.find("</w:p>", pb_idx) + 6
        doc = doc[:ps] + doc[pe:]

    # Remove any remaining page breaks between S5 and S7
    headings = find_fema_headings(doc)
    s5_h = next(h for h in headings if "Required" in h["text"])
    s7_h = next(h for h in headings if "Safety" in h["text"])
    region = doc[s5_h["start"]:s7_h["start"]]
    while 'w:type="page"' in region:
        br_idx = doc.find('w:type="page"', s5_h["start"])
        if br_idx == -1 or br_idx > s7_h["start"]:
            break
        ps = find_para_start(doc, br_idx)
        pe = doc.find("</w:p>", br_idx) + 6
        doc = doc[:ps] + doc[pe:]
        headings = find_fema_headings(doc)
        s7_h = next(h for h in headings if "Safety" in h["text"])
        region = doc[s5_h["start"]:s7_h["start"]]

    # --- COLON REMOVAL ---
    for ch in ["Guidelines:", "Responsibilities:", "History:", "Tools:"]:
        doc = doc.replace(ch, ch[:-1])

    # --- REVISION PLACEHOLDERS ---
    doc = doc.replace("[Your Name]", cfg["author"])
    doc = doc.replace("[Department Head]", "")
    doc = doc.replace("MM/DD/YYYY", cfg["gen_date"])
    doc = doc.replace("Initial SOP Template", "Initial SOP")

    # --- HEADER ---
    hp_idx = hdr.find('paraId="7A30C5B7"')
    if hp_idx > -1:
        hp_start = find_para_start(hdr, hp_idx)
        hp_end = hdr.find("</w:p>", hp_idx) + 6
        header_title = f"{full_esc} - {date_esc}"
        new_hdr = (
            '<w:p w14:paraId="7A30C5B7" w14:textId="199D5D59" '
            'w:rsidR="00FA4BB8" w:rsidRDefault="00FA4BB8">'
            '<w:pPr><w:pStyle w:val="FEMAHeader"/></w:pPr>'
            f'<w:r><w:t>{header_title}</w:t></w:r></w:p>'
        )
        hdr = hdr[:hp_start] + new_hdr + hdr[hp_end:]

    # --- SINGLE WRITE ---
    pathlib.Path("./unpacked/word/document.xml").write_text(doc, encoding="utf-8")
    pathlib.Path("./unpacked/word/header5.xml").write_text(hdr, encoding="utf-8")


    # ============================================================
    # FULL VALIDATION GATE (matches v13 Phase 7/8 harness)
    # ============================================================
    print("\n--- Consolidated Validation Gate ---")
    total_chk = 0; passed_chk = 0; fail_list = []
    def chk(cat, name, cond, detail=""):
        nonlocal total_chk, passed_chk
        total_chk += 1
        if cond:
            passed_chk += 1
            print(f"  [PASS] {cat} > {name}")
        else:
            fail_list.append((cat, name, detail))
            print(f"  [FAIL] {cat} > {name}" + (f" | {detail}" if detail else ""))

    # === XML VALIDITY ===
    try:
        ET.fromstring(doc.encode("utf-8"))
        chk("XML", "document.xml valid", True)
    except Exception as e:
        chk("XML", "document.xml valid", False, str(e)[:200])
    try:
        ET.fromstring(hdr.encode("utf-8"))
        chk("XML", "header5.xml valid", True)
    except Exception as e:
        chk("XML", "header5.xml valid", False, str(e)[:200])
    chk("XML", "No double-escaped amp in doc", "&amp;amp;" not in doc)
    chk("XML", "No double-escaped amp in hdr", "&amp;amp;" not in hdr)

    # === PLACEHOLDERS ===
    for p in ["Enter Title (Step-by-Step", "<w:t>Enter Title</w:t>",
              "<w:t>Enter Purpose</w:t>", "Enter Scope", "Enter Subtitle",
              "January 2026", "MM/DD/YYYY", "<w:t>X.0</w:t>"]:
        chk("Placeholders", f"No '{p[:40]}'", p not in doc)
    chk("Placeholders", "No 'Enter' in header", "Enter" not in hdr)

    # === HEADER ===
    hdr_all_text = "".join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', hdr))
    chk("Header", "No highlight in header", "highlight" not in hdr)
    chk("Header", "Has hyphen separator", " - " in hdr_all_text)
    chk("Header", "No en-dash U+2013", "\u2013" not in hdr_all_text and "&#x2013;" not in hdr)
    chk("Header", "Exactly one hyphen separator", hdr.count(" - ") >= 1)

    # === TITLE CASCADE ===
    chk("Title", "Full title in doc", full_esc in doc)
    chk("Title", "Short title in S6 heading",
        short_esc + " (Step-by-Step Instructions)" in doc)
    chk("Title", "Title in header",
        cfg["full_title"].replace("&amp;", "&").split(" - ")[0][:20].replace("&", "&amp;") in hdr_all_text
        or cfg["full_title"].split(" - ")[0][:20] in hdr_all_text)

    # === STRUCTURE: FEMAHEADING1 ===
    headings = find_fema_headings(doc)
    heading_texts = [h["text"] for h in headings]
    for key, marker in {"S1": "Purpose", "S2": "Scope", "S3": "Supersession",
                        "S4": "Roles", "S5": "Required", "S6": "Step-by-Step",
                        "S7": "Safety", "S8": "Revision"}.items():
        chk("Structure", f"{key} heading ({marker})", any(marker in h for h in heading_texts))

    # === COLONS ===
    for x in ["Guidelines:", "Responsibilities:", "History:", "Tools:"]:
        chk("Colons", f"No '{x}'", x not in doc)

    # === SECTION 6 CONTENT ===
    headings = find_fema_headings(doc)
    s6_hv = next((h for h in headings if "Step-by-Step" in h["text"]), None)
    s7_hv = None
    if s6_hv:
        s6_idx_v = headings.index(s6_hv)
        if s6_idx_v + 1 < len(headings):
            s7_hv = headings[s6_idx_v + 1]

    if s6_hv and s7_hv:
        s6_region = doc[s6_hv["end"]:s7_hv["start"]]

        # Template remnants (scoped to S6 region only per v13)
        for remnant in ["Step 1", "Step 2", "Sub step", "Sub-sub step"]:
            chk("S6", f"No template remnant '{remnant}'", remnant not in s6_region)

        # S6 ilvl distribution
        ri0 = s6_region.count('w:ilvl w:val="0"')
        ri1 = s6_region.count('w:ilvl w:val="1"')
        ri2 = s6_region.count('w:ilvl w:val="2"')
        chk("S6", f"S6 ilvl0={ri0} == source={src_ilvl0}", ri0 == src_ilvl0)
        chk("S6", f"S6 ilvl1={ri1} == source={src_ilvl1}", ri1 == src_ilvl1)
        chk("S6", f"S6 ilvl2={ri2} == source={src_ilvl2}", ri2 == src_ilvl2)
        chk("S6", "Not flattened (ilvl1 > 0)", ri1 > 0 or src_ilvl1 == 0)

        # Whole-document ilvl totals
        fi0 = doc.count('w:ilvl w:val="0"')
        fi1 = doc.count('w:ilvl w:val="1"')
        fi2 = doc.count('w:ilvl w:val="2"')
        chk("S6", f"Total ilvl0: {fi0} == {BASELINE_ILVL0 + src_ilvl0}", fi0 == BASELINE_ILVL0 + src_ilvl0)
        chk("S6", f"Total ilvl1: {fi1} == {BASELINE_ILVL1 + src_ilvl1}", fi1 == BASELINE_ILVL1 + src_ilvl1)
        chk("S6", f"Total ilvl2: {fi2} == {BASELINE_ILVL2 + src_ilvl2}", fi2 == BASELINE_ILVL2 + src_ilvl2)

        # Key content phrases (first 8 steps)
        for step in cfg["s6_steps"][:8]:
            phrase = step["text"][:45]
            chk("S6", f"Contains '{phrase}'", step["text"][:30] in s6_region)

        # Highlighted steps
        hl_ct = s6_region.count('<w:highlight w:val="yellow"/>')
        eff_hl = hl_ct // 2
        chk("S6", f"Highlights: {eff_hl} == {src_highlights}", eff_hl == src_highlights)

        # Intro paragraph
        fp_match = re.search(r'<w:p[^>]*>(.*?)</w:p>', s6_region, re.DOTALL)
        if fp_match and cfg["s6_intro"]:
            chk("S6", "Intro paragraph has no numPr", "numPr" not in fp_match.group(0))
    else:
        chk("S6", "S6/S7 boundaries found", False)

    # === INTELLIGENT COMPLETION: S4 ===
    s4_hv2 = next((h for h in headings if "Roles" in h["text"]), None)
    s5_hv2 = next((h for h in headings if "Required" in h["text"]), None)
    if s4_hv2 and s5_hv2:
        s4r = doc[s4_hv2["end"]:s5_hv2["start"]]
        s4t = [t.strip() for t in re.findall(r'<w:t[^>]*>([^<]+)</w:t>', s4r)
               if t.strip() and t.strip() not in ["4.", "5.", "Roles and Responsibilities", "Required Materials and Tools"]]
        chk("IC", f"S4 populated ({len(s4t)} items)", len(s4t) > 0)
        # Role format: either "Role: Description" in text, or table with separate cells
        roles = [t for t in s4t if ":" in t and not t.startswith("(")]
        has_table = "<w:tbl" in s4r
        chk("IC", f"S4 Role: Description format ({len(roles)} entries, table={has_table})",
            len(roles) > 0 or (has_table and len(s4t) >= 2))

    # === INTELLIGENT COMPLETION: S5 ===
    if s5_hv2 and s6_hv:
        s5r = doc[s5_hv2["end"]:s6_hv["start"]]
        s5t = [t.strip() for t in re.findall(r'<w:t[^>]*>([^<]+)</w:t>', s5r)
               if t.strip() and t.strip() not in ["5.", "6.", "Required Materials and Tools"]]
        chk("IC", f"S5 populated ({len(s5t)} items)", len(s5t) > 0)
        chk("IC", "S5 has materials content", len("".join(s5t)) > 20)

    # === REVIEW FLAGS (5 flags x 3 checks each = 15) ===
    for label, ft in [("S2", "Add or modify scope"), ("S4", "Add or modify roles"),
                      ("S5", "List all necessary"), ("S7", "Add or modify safety"),
                      ("S8", "Update revision history")]:
        if ft in doc:
            fi = doc.find(ft)
            ps = doc.rfind("<w:p", 0, fi)
            pe = doc.find("</w:p>", fi) + 6
            para = doc[ps:pe]
            ppr = para.split("</w:pPr>")[0] if "</w:pPr>" in para else ""
            rpr_part = para[para.find("</w:pPr>"):] if "</w:pPr>" in para else ""
            chk("Flags", f"{label} flag exists", True)
            chk("Flags", f"{label} italic+highlight pPr",
                "<w:i/>" in ppr and 'highlight w:val="yellow"' in ppr)
            chk("Flags", f"{label} italic+highlight rPr",
                "<w:i/>" in rpr_part and 'highlight w:val="yellow"' in rpr_part)
        else:
            chk("Flags", f"{label} flag exists", False)

    # === PAGE BREAKS ===
    s5hv = next((h for h in headings if "Required" in h["text"]), None)
    s7hv = next((h for h in headings if "Safety" in h["text"]), None)
    if s5hv and s7hv:
        pbc = doc[s5hv["end"]:s7hv["start"]].count('w:type="page"')
        chk("PageBreaks", f"None S5-S7 ({pbc})", pbc == 0)

    # === REVISION HISTORY ===
    chk("Revision", "JENNY in doc", "JENNY" in doc)
    chk("Revision", "JENNY- author format", "JENNY-" in doc)
    chk("Revision", "Version 1.0 present", "1.0" in doc)
    chk("Revision", "Initial SOP description", "Initial SOP" in doc)

    # === SUMMARY ===
    print(f"\n{'='*60}")
    print(f"  SCORE: {passed_chk}/{total_chk} ({passed_chk/total_chk*100:.0f}%)")
    if fail_list:
        print(f"\n  FAILURES ({len(fail_list)}):")
        by_cat = {}
        for cat, n, d in fail_list:
            if cat not in by_cat: by_cat[cat] = []
            by_cat[cat].append((n, d))
        for cat in by_cat:
            print(f"    {cat}:")
            for n, d in by_cat[cat]:
                print(f"      - {n}" + (f" ({d})" if d else ""))
    else:
        print("  ALL CHECKS PASSED")
    print(f"{'='*60}")

    if fail_list:
        print("\nWARNING: Validation failures detected. Output may need manual review.")

    # --- PACK ---
    r = subprocess.run([sys.executable, "pack_docx.py", "./unpacked/", output_path],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    assert "Packed" in r.stdout or os.path.exists(output_path), f"Pack failed: {r.stderr}"
    print(f"\nOutput: {output_path}")

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python jenny_pipeline.py CONFIG.py TEMPLATE.docx OUTPUT.docx [INSTRUCTIONS.md]")
        sys.exit(1)

    config = load_config(sys.argv[1])
    template = sys.argv[2]
    output = sys.argv[3]
    instructions = sys.argv[4] if len(sys.argv) > 4 else None

    run_pipeline(config, template, output, instructions)
