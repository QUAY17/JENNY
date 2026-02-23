import { useState, useRef, useCallback } from "react";

const API_BASE = "http://localhost:5000";

const colors = {
  bg: "#0a0f1a",
  surface: "#111827",
  surfaceAlt: "#1a2332",
  border: "#2a3a4f",
  borderFocus: "#3b82f6",
  text: "#e2e8f0",
  textMuted: "#94a3b8",
  textDim: "#64748b",
  accent: "#3b82f6",
  accentHover: "#2563eb",
  success: "#10b981",
  successBg: "#064e3b",
  warning: "#f59e0b",
  warningBg: "#78350f",
  error: "#ef4444",
  errorBg: "#7f1d1d",
  generate: "#10b981",
  generateHover: "#059669",
};

const font = "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace";
const fontBody = "'IBM Plex Sans', -apple-system, sans-serif";

function StatusBadge({ status }) {
  const map = {
    idle: { label: "IDLE", bg: colors.surfaceAlt, color: colors.textDim },
    uploading: { label: "UPLOADING", bg: colors.warningBg, color: colors.warning },
    extracting: { label: "EXTRACTING", bg: "#1e3a5f", color: colors.accent },
    review: { label: "REVIEW CONFIG", bg: colors.warningBg, color: colors.warning },
    generating: { label: "GENERATING", bg: "#1e3a5f", color: colors.accent },
    complete: { label: "COMPLETE", bg: colors.successBg, color: colors.success },
    error: { label: "ERROR", bg: colors.errorBg, color: colors.error },
  };
  const s = map[status] || map.idle;
  return (
    <span style={{
      display: "inline-block", padding: "4px 12px", borderRadius: 4,
      background: s.bg, color: s.color, fontFamily: font, fontSize: 11,
      fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
    }}>{s.label}</span>
  );
}

function FileUpload({ label, accept, onFile, file, id }) {
  const ref = useRef();
  return (
    <div style={{
      border: `1px dashed ${file ? colors.success : colors.border}`,
      borderRadius: 8, padding: 20, textAlign: "center", cursor: "pointer",
      background: file ? "rgba(16,185,129,0.05)" : "transparent",
      transition: "all 0.2s",
    }}
      onClick={() => ref.current?.click()}
      onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
      onDrop={(e) => { e.preventDefault(); e.stopPropagation(); if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]); }}
    >
      <input ref={ref} type="file" accept={accept} style={{ display: "none" }} id={id}
        onChange={(e) => { if (e.target.files[0]) onFile(e.target.files[0]); }} />
      <div style={{ fontSize: 13, fontFamily: fontBody, color: file ? colors.success : colors.textMuted, marginBottom: 4 }}>
        {file ? file.name : label}
      </div>
      {file && <div style={{ fontSize: 11, color: colors.textDim }}>{(file.size / 1024).toFixed(1)} KB</div>}
      {!file && <div style={{ fontSize: 11, color: colors.textDim }}>Click or drag to upload</div>}
    </div>
  );
}

function LogPanel({ logs }) {
  const ref = useRef();
  const prevLen = useRef(0);
  if (logs.length !== prevLen.current) {
    prevLen.current = logs.length;
    setTimeout(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, 50);
  }
  return (
    <div ref={ref} style={{
      background: "#000", borderRadius: 8, padding: 16, fontFamily: font, fontSize: 12,
      lineHeight: 1.6, maxHeight: 300, overflowY: "auto", color: colors.textMuted,
      border: `1px solid ${colors.border}`,
    }}>
      {logs.map((l, i) => (
        <div key={i} style={{
          color: l.type === "error" ? colors.error
            : l.type === "success" ? colors.success
            : l.type === "info" ? colors.accent
            : colors.textMuted,
        }}>
          <span style={{ color: colors.textDim, marginRight: 8 }}>{l.time}</span>
          {l.msg}
        </div>
      ))}
      {logs.length === 0 && <span style={{ color: colors.textDim }}>Waiting for input...</span>}
    </div>
  );
}

function ConfigEditor({ config, onChange }) {
  if (!config) return null;

  const renderField = (key, value, path = []) => {
    const fullPath = [...path, key];
    const pathStr = fullPath.join(".");

    if (Array.isArray(value) && value.length > 0 && typeof value[0] === "object" && value[0].text !== undefined) {
      const ilvlLabels = {
        0: "1. 2. 3.",
        1: "a. b. c.",
        2: "i. ii. iii.",
        3: "1) 2) 3)",
      };
      const ilvlNames = {
        0: "Main Step",
        1: "Sub-step",
        2: "Sub-sub",
        3: "Sub-sub-sub",
      };
      return (
        <div key={pathStr} style={{ marginBottom: 16 }}>
          <label style={{ display: "block", fontSize: 11, fontFamily: font, color: colors.accent, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            {key} ({value.length} steps)
          </label>
          <div style={{ fontSize: 10, fontFamily: font, color: colors.textDim, marginBottom: 6 }}>
            Indent levels: 1. 2. 3. = Main Step | a. b. c. = Sub-step | i. ii. iii. = Sub-sub | 1) 2) 3) = Sub-sub-sub
          </div>
          <div style={{ maxHeight: 300, overflowY: "auto", border: `1px solid ${colors.border}`, borderRadius: 6, padding: 8 }}>
            {value.map((step, i) => {
              const hlColor = step.highlight_color || "yellow";
              const isHighlighted = step.highlighted;
              const hlBorder = isHighlighted
                ? (hlColor === "cyan" ? "#06b6d4" : colors.warning)
                : colors.border;
              const hlBg = isHighlighted
                ? (hlColor === "cyan" ? "rgba(6,182,212,0.1)" : "rgba(245,158,11,0.1)")
                : colors.surfaceAlt;
              return (
              <div key={i} style={{
                display: "grid", gridTemplateColumns: "70px 1fr 90px",
                gap: 6, marginBottom: 4, alignItems: "start",
                paddingLeft: step.ilvl * 20,
              }}>
                <span style={{
                  fontSize: 10, fontFamily: font, color: isHighlighted ? hlBorder : colors.textDim,
                  paddingTop: 6, fontWeight: isHighlighted ? 600 : 400,
                }}>
                  {ilvlNames[step.ilvl] || "?"}{isHighlighted ? ` [${hlColor}]` : ""}
                </span>
                <input style={{
                  width: "100%", padding: "4px 8px", background: hlBg,
                  border: `1px solid ${hlBorder}`, borderRadius: 4, color: colors.text,
                  fontFamily: fontBody, fontSize: 12,
                }}
                  value={step.text}
                  onChange={(e) => {
                    const newSteps = [...value];
                    newSteps[i] = { ...step, text: e.target.value };
                    onChange(fullPath, newSteps);
                  }}
                />
                <select style={{
                  padding: "4px 2px", background: colors.surfaceAlt, border: `1px solid ${colors.border}`,
                  borderRadius: 4, color: colors.text, fontFamily: font, fontSize: 11,
                }}
                  value={step.ilvl}
                  onChange={(e) => {
                    const newSteps = [...value];
                    newSteps[i] = { ...step, ilvl: parseInt(e.target.value) };
                    onChange(fullPath, newSteps);
                  }}
                >
                  <option value={0}>1. 2. 3. (Main)</option>
                  <option value={1}>a. b. c. (Sub)</option>
                  <option value={2}>i. ii. iii. (Sub-sub)</option>
                  <option value={3}>1) 2) 3) (Sub-sub-sub)</option>
                </select>
              </div>
              );
            })}
          </div>
        </div>
      );
    }

    if (Array.isArray(value)) {
      return (
        <div key={pathStr} style={{ marginBottom: 12 }}>
          <label style={{ display: "block", fontSize: 11, fontFamily: font, color: colors.accent, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            {key} ({value.length} items)
          </label>
          {value.map((item, i) => (
            <textarea key={i} style={{
              width: "100%", padding: "6px 10px", background: colors.surfaceAlt,
              border: `1px solid ${colors.border}`, borderRadius: 4, color: colors.text,
              fontFamily: fontBody, fontSize: 12, marginBottom: 4, resize: "vertical",
              minHeight: 36,
            }}
              value={item}
              onChange={(e) => {
                const newArr = [...value];
                newArr[i] = e.target.value;
                onChange(fullPath, newArr);
              }}
            />
          ))}
        </div>
      );
    }

    if (typeof value === "string") {
      const isLong = value.length > 100;
      const Comp = isLong ? "textarea" : "input";
      return (
        <div key={pathStr} style={{ marginBottom: 12 }}>
          <label style={{ display: "block", fontSize: 11, fontFamily: font, color: colors.accent, marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            {key}
          </label>
          <Comp style={{
            width: "100%", padding: "6px 10px", background: colors.surfaceAlt,
            border: `1px solid ${colors.border}`, borderRadius: 4, color: colors.text,
            fontFamily: fontBody, fontSize: 12, resize: isLong ? "vertical" : "none",
            ...(isLong ? { minHeight: 60 } : {}),
          }}
            value={value}
            onChange={(e) => onChange(fullPath, e.target.value)}
          />
        </div>
      );
    }
    return null;
  };

  const fieldOrder = [
    "full_title", "short_title", "structure_type", "cover_date",
    "extraction_notes", "purpose", "scope", "s6_intro", "s6_steps",
    "s4_roles", "s5_materials", "s7_guidelines", "s3_supersession"
  ];

  return (
    <div style={{ maxHeight: 500, overflowY: "auto", paddingRight: 8 }}>
      {fieldOrder.map(key => config[key] !== undefined ? renderField(key, config[key]) : null)}
    </div>
  );
}

export default function JennyApp() {
  const [template, setTemplate] = useState(null);
  const [draft, setDraft] = useState(null);
  const [status, setStatus] = useState("idle");
  const [config, setConfig] = useState(null);
  const [logs, setLogs] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [validationResult, setValidationResult] = useState(null);
  const [downloadUrl, setDownloadUrl] = useState(null);
  const [modelLabel, setModelLabel] = useState("");

  const log = useCallback((msg, type = "log") => {
    const time = new Date().toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
    setLogs(prev => [...prev, { time, msg, type }]);
  }, []);

  const uploadFile = async (file, field) => {
    const formData = new FormData();
    formData.append(field, file);
    if (sessionId) formData.append("session_id", sessionId);

    try {
      const resp = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: formData });
      const data = await resp.json();
      setSessionId(data.session_id);
      log(`Uploaded ${field}: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`, "success");
      return data;
    } catch (e) {
      log(`Upload failed: ${e.message}`, "error");
      return null;
    }
  };

  const handleTemplate = async (file) => { setTemplate(file); await uploadFile(file, "template"); };
  const handleDraft = async (file) => { setDraft(file); await uploadFile(file, "draft"); };

  const extractConfig = async () => {
    if (!sessionId || !draft || !template) { log("Upload both files first", "error"); return; }
    setStatus("extracting");
    log("Phase 0: Backend reading .docx + calling LLM for extraction...", "info");

    try {
      const resp = await fetch(`${API_BASE}/api/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const data = await resp.json();

      if (!resp.ok) {
        log(`Extraction error: ${data.error}`, "error");
        if (data.raw_response) log(`Raw: ${data.raw_response.slice(0, 300)}`, "error");
        setStatus("error");
        return;
      }

      log(`Draft: ${data.draft_chars} chars extracted from .docx`, "success");
      const s = data.stats;
      const ilvlParts = [`Main(1.2.3.)=${s.ilvl0}`, `Sub(a.b.c.)=${s.ilvl1}`, `Sub-sub(i.ii.)=${s.ilvl2}`];
      if (s.ilvl3) ilvlParts.push(`Sub-sub-sub=${s.ilvl3}`);
      log(`Config: ${s.total_steps} steps (${ilvlParts.join(", ")}), ${s.highlighted} highlighted`, "success");
      log(`Roles: ${s.roles}, Guidelines: ${s.guidelines}`, "success");
      if (data.model) {
        setModelLabel(data.model);
        log(`Model: ${data.model}`, "info");
      }
      (data.issues || []).forEach(i => log(`SANITIZED: ${i}`, "info"));
      (data.config.extraction_notes || []).forEach(n => log(`NOTE: ${n}`, "info"));

      setConfig(data.config);
      setStatus("review");
      log("Config ready for review. Edit if needed, then press GENERATE.", "info");
    } catch (e) {
      log(`Extraction failed: ${e.message}`, "error");
      setStatus("error");
    }
  };

  const handleConfigChange = (path, value) => {
    setConfig(prev => {
      const next = JSON.parse(JSON.stringify(prev));
      let obj = next;
      for (let i = 0; i < path.length - 1; i++) obj = obj[path[i]];
      obj[path[path.length - 1]] = value;
      return next;
    });
  };

  const generateSOP = async () => {
    if (!sessionId || !config) return;
    setStatus("generating");
    setDownloadUrl(null);
    setValidationResult(null);
    log("Sending config to pipeline...", "info");

    try {
      const resp = await fetch(`${API_BASE}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, config }),
      });
      const data = await resp.json();

      if (!resp.ok || !data.success) {
        log(`Pipeline failed: ${data.error || "Unknown error"}`, "error");
        if (data.log) data.log.split("\n").filter(l => l.trim()).forEach(l => log(l, l.includes("[FAIL]") ? "error" : "log"));
        setStatus("error");
        return;
      }

      data.log.split("\n").filter(l => l.trim()).forEach(l => {
        if (l.includes("[PASS]")) log(l.trim(), "success");
        else if (l.includes("[FAIL]")) log(l.trim(), "error");
        else if (l.includes("SCORE:") || l.includes("ALL CHECKS")) log(l.trim(), "success");
        else log(l.trim());
      });

      const scoreMatch = data.score?.match(/(\d+)\/(\d+)\s*\((\d+)%\)/);
      setValidationResult({
        score: scoreMatch ? `${scoreMatch[1]}/${scoreMatch[2]}` : data.score,
        pct: scoreMatch ? parseInt(scoreMatch[3]) : 0,
        ilvl: {
          i0: config.s6_steps?.filter(s => s.ilvl === 0).length || 0,
          i1: config.s6_steps?.filter(s => s.ilvl === 1).length || 0,
          i2: config.s6_steps?.filter(s => s.ilvl === 2).length || 0,
          i3: config.s6_steps?.filter(s => s.ilvl === 3).length || 0,
        },
        title: config.short_title,
      });
      setDownloadUrl(`${API_BASE}${data.download_url}`);
      setStatus("complete");
      log("SOP generated. Click DOWNLOAD to save.", "success");
    } catch (e) {
      log(`Generate failed: ${e.message}`, "error");
      setStatus("error");
    }
  };

  const resetAll = () => {
    setTemplate(null); setDraft(null); setConfig(null); setStatus("idle");
    setLogs([]); setSessionId(null); setValidationResult(null); setDownloadUrl(null); setModelLabel("");
  };

  return (
    <div style={{ minHeight: "100vh", background: colors.bg, color: colors.text, fontFamily: fontBody }}>
      {/* Header */}
      <div style={{
        borderBottom: `1px solid ${colors.border}`, padding: "16px 32px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ fontFamily: font, fontSize: 20, fontWeight: 700, color: colors.success, letterSpacing: "0.05em" }}>JENNY</span>
          <span style={{ fontSize: 11, color: colors.textDim, fontFamily: font }}>FEMA Document Automation</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <StatusBadge status={status} />
          {status !== "idle" && (
            <button onClick={resetAll} style={{
              padding: "4px 12px", borderRadius: 4, border: `1px solid ${colors.border}`,
              background: "transparent", color: colors.textDim, fontFamily: font, fontSize: 11, cursor: "pointer",
            }}>RESET</button>
          )}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "380px 1fr", minHeight: "calc(100vh - 57px)" }}>
        {/* Left Panel */}
        <div style={{ borderRight: `1px solid ${colors.border}`, padding: 24, display: "flex", flexDirection: "column", gap: 20 }}>
          <div>
            <div style={{ fontSize: 11, fontFamily: font, color: colors.textDim, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.1em" }}>1. Upload Files</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <FileUpload label="FEMA SOP Template (.docx)" accept=".docx" onFile={handleTemplate} file={template} id="template" />
              <FileUpload label="Source SOP Draft (.docx)" accept=".docx" onFile={handleDraft} file={draft} id="draft" />
            </div>
          </div>

          <div>
            <div style={{ fontSize: 11, fontFamily: font, color: colors.textDim, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.1em" }}>2. Extract Config</div>
            <button disabled={!template || !draft || status === "extracting"} onClick={extractConfig}
              style={{
                width: "100%", padding: "12px 20px", borderRadius: 6, border: "none",
                background: (!template || !draft) ? colors.surfaceAlt : colors.accent,
                color: (!template || !draft) ? colors.textDim : "#fff",
                fontFamily: font, fontSize: 13, fontWeight: 600,
                cursor: (!template || !draft) ? "default" : "pointer",
                opacity: status === "extracting" ? 0.7 : 1,
              }}>
              {status === "extracting" ? "EXTRACTING..." : "EXTRACT CONFIG"}
            </button>
            <div style={{ fontSize: 10, color: colors.textDim, marginTop: 6, fontFamily: font }}>{modelLabel ? `Model: ${modelLabel}` : "Calls LLM via Anthropic API"}</div>
          </div>

          <div>
            <div style={{ fontSize: 11, fontFamily: font, color: colors.textDim, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.1em" }}>3. Generate SOP</div>
            <button disabled={status !== "review"} onClick={generateSOP}
              style={{
                width: "100%", padding: "16px 20px", borderRadius: 6, border: "none",
                background: status !== "review" ? colors.surfaceAlt : colors.generate,
                color: status !== "review" ? colors.textDim : "#fff",
                fontFamily: font, fontSize: 15, fontWeight: 700,
                cursor: status !== "review" ? "default" : "pointer",
                boxShadow: status === "review" ? "0 0 20px rgba(16,185,129,0.3)" : "none",
              }}>
              GENERATE SOP
            </button>
          </div>

          {validationResult && (
            <div style={{
              background: validationResult.pct === 100 ? colors.successBg : colors.warningBg,
              border: `1px solid ${validationResult.pct === 100 ? colors.success : colors.warning}`,
              borderRadius: 8, padding: 16,
            }}>
              <div style={{ fontFamily: font, fontSize: 22, fontWeight: 700, marginBottom: 8, color: validationResult.pct === 100 ? colors.success : colors.warning }}>
                {validationResult.score} ({validationResult.pct}%)
              </div>
              <div style={{ fontSize: 12, marginBottom: 4, color: validationResult.pct === 100 ? colors.success : colors.warning }}>
                {validationResult.pct === 100 ? "ALL CHECKS PASSED" : "REVIEW FAILURES IN LOG"}
              </div>
              <div style={{ fontSize: 11, color: colors.textMuted, fontFamily: font }}>
                Main Steps (1.2.3.): {validationResult.ilvl.i0} | Sub (a.b.c.): {validationResult.ilvl.i1} | Sub-sub (i.ii.iii.): {validationResult.ilvl.i2}{validationResult.ilvl.i3 ? ` | Sub-sub-sub: ${validationResult.ilvl.i3}` : ""}
              </div>
              {downloadUrl && (
                <a href={downloadUrl} download style={{
                  display: "block", marginTop: 12, padding: "10px 16px",
                  background: validationResult.pct === 100 ? colors.generate : colors.warning,
                  borderRadius: 6, textAlign: "center", textDecoration: "none",
                  fontFamily: font, fontSize: 13, fontWeight: 700, color: "#fff",
                }}>
                  DOWNLOAD .DOCX
                </a>
              )}
            </div>
          )}

          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 11, fontFamily: font, color: colors.textDim, marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.1em" }}>Pipeline Log</div>
            <LogPanel logs={logs} />
          </div>
        </div>

        {/* Right Panel */}
        <div style={{ padding: 24, overflowY: "auto" }}>
          <div style={{ fontSize: 11, fontFamily: font, color: colors.textDim, marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.1em" }}>
            Config Review {config ? `-- ${config.s6_steps?.length || 0} steps extracted` : ""}
          </div>
          {!config && (
            <div style={{
              display: "flex", alignItems: "center", justifyContent: "center", height: 400,
              color: colors.textDim, fontSize: 14, border: `1px dashed ${colors.border}`, borderRadius: 8,
            }}>
              Upload files and extract config to begin
            </div>
          )}
          {config && <ConfigEditor config={config} onChange={handleConfigChange} />}
        </div>
      </div>
    </div>
  );
}
