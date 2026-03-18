# Efficiency by Design: Reducing AI Cost Through Smart Architecture

**Jennifer Minnich | March 2026**

---

## The Problem With AI-First Thinking

The default approach to building AI-powered applications is to route everything through the model: parse the document, restructure it, generate the output, validate the result. Each of these steps burns tokens - and tokens cost money, time, and energy. A single formatted document generation run through a naive "let the LLM do everything" pipeline could consume 50,000–100,000+ tokens per document, with unpredictable output quality and no structural guarantees.

This is the equivalent of hiring an architect to also carry the bricks.

## The Smart Architecture Approach: LLM as Specialist, Not Generalist

JENNY was designed around a simple principle: **use the LLM only for tasks that require language understanding (what LLMs are actually good at), and use deterministic code for everything else.**

The architecture splits document generation into two distinct phases:

**Phase 1 - Extraction (LLM):** The model reads a source draft and extracts structured data: titles, steps, roles, materials, guidelines. This is a text comprehension task - perfect for an LLM. The output is a flat Python dictionary, not a formatted document.

**Phase 2 - Generation (Code):** A deterministic Python pipeline takes that dictionary and builds the final `.docx` by direct XML manipulation of an existing template. Every heading, paragraph, numbered list, image, hyperlink, header, footer, and table of contents entry is placed programmatically. Zero LLM involvement, zero cost.

The result:

| Metric | LLM-Heavy Approach* | JENNY Architecture |
|---|---|---|
| Input tokens per document | 40,000–100,000 | 3,000–8,000 |
| Output tokens per document | 30,000–100,000 | 1,500–3,000 |
| LLM calls per document | 2–4 (generation + retries) | 1 (extraction only) |
| Output consistency | Variable | Deterministic |
| Template compliance | Best-effort | Guaranteed |
| Image/hyperlink handling | Unreliable | Exact |
| Cost per SOP (Claude Sonnet) | ~$1.00–1.80 | ~$0.03–0.08 |

That is a **15–25x reduction in per-document cost** with higher output quality.

*\*LLM-Heavy estimates based on Claude 3.5 Sonnet pricing ($3/1M input, $15/1M output) for a pipeline that sends template XML, draft text, and formatting instructions to the model and generates the full document output, assuming 1–2 correction passes for formatting errors. JENNY costs are measured from production extractions.*

## The Design Principles

**1. Deterministic where possible, intelligent where necessary.**
XML template manipulation, image injection, hyperlink wiring, nested list formatting - these are solved problems in computer science. They don't require intelligence. They require precision. Code delivers precision.

**2. Narrow the LLM's job to its smallest useful scope.**
The text extraction prompt asks the model to do one thing: read text and fill a schema. It does not ask the model to generate XML, format documents, make layout decisions, or reason about template structure. A constrained task produces a reliable result.

**3. Validate the LLM's work then let the code run.**
The LLM's output can be validated when imported into the app. After that point, the pipeline is deterministic - producing consistent and reliable output because the logic is implemented in code rather than dependent on model variability. No retry loops or self-correction passes. No extra tokens spent fixing formatting the model got wrong.

**4. Design for the external LLM path.**
The smart architecture decouples the LLM call from the code. Therefore, JENNY works with *any* LLM - ChatGPT, Claude, Copilot, or others. This means the token cost can be zero for organizations that already have LLM access.

## Productivity Per Token: A New Engineering Metric

When we evaluate AI-integrated systems, we should measure **productivity per token** - not just whether the system uses AI, but how efficiently it converts token spend into useful output.

A chatbot that generates an entire document end-to-end may feel impressive, but most of the token spend goes to formatting, not thinking. Moving the formatting into code cuts the cost 25x while producing better, more consistent output.

This is the disciplined application of AI. The same engineering instinct that prevents us from using a database query to sort three items in memory should prevent us from using an LLM to indent a bullet point.

## Broader Application

This architecture pattern - **LLM for comprehension, code for construction** - applies far beyond document generation:

- **Data pipelines:** LLM classifies or extracts from unstructured input; code transforms, validates, and loads.
- **Report generation:** LLM summarizes findings; code builds charts, tables, and formatted output.
- **Form processing:** LLM reads and interprets submitted forms; code routes, validates, and stores the data.

The organizations that will get the most value from AI are not the ones that use it the most - they are the ones that use it the most precisely.

---

*Arch Systems Inc. builds intelligent systems for federal agencies. JENNY is a prototype document automation tool developed for FEMA's Incident Workforce Academy.*
