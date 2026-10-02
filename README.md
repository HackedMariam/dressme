# DressMe

**Your smart wardrobe, your personal fashion assistant.**

DressMe is a smart wardrobe ecosystem designed primarily for the **Tunisian market**. The idea is simple: most people own more clothes than they wear, forget what they already own, and end up buying duplicates. DressMe turns a physical wardrobe into a structured, queryable digital one, then uses that understanding to help with everyday decisions — what to wear, what to pack, what to buy, and what to let go.

> **Project status — please read first.**
> This repository currently contains the **UI / Figma prototype** of DressMe. It is the visual and UX reference for the future application, not the application itself. Product, architectural, and AI decisions are still under discussion and are **not finalized**. Nothing described in the roadmap or AI sections below is implemented yet.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Business Objectives](#business-objectives)
- [AI & Multi-Agent Architecture](#ai--multi-agent-architecture)
- [Prototype](#prototype)
- [Screens](#screens)
- [Current Status](#current-status)
- [Roadmap](#roadmap)
- [Repository Structure](#repository-structure)
- [Disclaimer / Project Status](#disclaimer--project-status)

---

## Project Overview

DressMe aims to combine four capability areas into a single personalized wardrobe ecosystem:

| Pillar | Role |
| --- | --- |
| **Computer Vision** | Understand a photo of a garment: detect it, segment it, remove the background, classify it, and extract attributes (category, color, pattern, material, season). |
| **Recommendation** | Match and rank items into outfits, packing lists, and purchase decisions based on compatibility rather than generic popularity. |
| **Contextual data** | Weather, destination, occasion, season, luggage constraints, budget, and the user's own style profile. |
| **AI agents** | Conversational and task-oriented agents that combine all of the above and explain their reasoning to the user. |

The end goal is an assistant that *understands* the user's wardrobe and preferences rather than just browsing a catalog. It should be able to answer questions like "what do I wear to a dinner party?" or "what am I missing from my wardrobe?" using only what the user actually owns.

The target context is the Tunisian market: local climate ranges, a retail landscape that differs from Europe/North America, purchasing power constraints, and a fashion reality that is practical rather than trend-driven. Those constraints are a product requirement, not an afterthought.

**What this repository is:** the Figma-derived UI prototype that will serve as the reference implementation of the future frontend. The interface is already navigable and covers the main flows described below.

---

## Business Objectives

Seven business objectives (BOs) structure the product. Each is a distinct capability area rather than a UI screen.

### BO1 — Wardrobe Visibility

Make the wardrobe legible and structured. A user photographs their clothes; the system removes the background, detects the category, extracts attributes (color, material, pattern, season, style tags), and stores the item. Automatic extraction is never trusted blindly — the user can correct any field. The result is a wardrobe that can be searched, filtered, and sorted, plus a wear log that records what gets used and how often.

### BO2 — Outfit Recommendation

Suggest outfits built **only from what the user already owns**. Recommendations are conditioned on context: occasion, season, current weather, declared style preferences, and the compatibility of the pieces with each other (silhouette, color harmony, formality level, layering logic). The goal is fewer unused items, not more outfits.

### BO3 — Smart Packing

Turn a trip into a pack list. The system takes destination, dates, planned activities, dress code, and luggage constraints, then combines them with the user's wardrobe and the destination's weather forecast. It optimises for mix-and-match potential — fewest items, most combinations — and flags redundant pieces or items worth buying before departure.

### BO4 — Smart Purchasing

Act as a second opinion *before* a purchase. Given a screenshot, link, or description of an item, DressMe evaluates it against the existing wardrobe: does it fit the user's style, does it work with what they own, is it a near-duplicate of something they already have, does it fill a real gap, and does the price make sense relative to their spending pattern and budget.

### BO5 — Wardrobe Optimization

Give the user an objective view of what they own. Identify gaps (underrepresented categories), redundancy (items that duplicate each other), underused pieces (bought but rarely worn), wardrobe "mainstays" (high-rotation items), and structural issues such as too many of one colour or too few versatile layers. The output is insight, not instruction.

### BO6 — Decluttering & Wardrobe Management

Support keep / remove / reorganise decisions with evidence rather than impulse. Usage history, seasonal relevance, combination potential, and the user's own stated preferences are combined into a personalised recommendation per item, so the reasoning behind "you can let this go" is visible and arguable.

### BO7 — Fashion Inspiration & Discovery

Surface inspiration and shopping suggestions that remain grounded in the user's actual style and existing wardrobe. Discovery is filtered through the style profile, so it extends the user's taste rather than drifting into generic trend content, and it is aware of the occasion and season the user is dressing for.

---

## AI & Multi-Agent Architecture

DressMe is planned to evolve toward a **multi-agent architecture**: a set of specialised agents, each responsible for a bounded task, collaborating through an orchestration layer.

| Agent | Responsibility |
| --- | --- |
| **Wardrobe Analysis / Computer Vision Agent** | Garment detection, segmentation, background removal, classification, attribute extraction |
| **Outfit Recommendation Agent** | Assembles and scores outfits from the existing wardrobe given context |
| **Packing Agent** | Builds and optimises trip pack lists against weather, activities, and luggage limits |
| **Shopping / Purchase Assistant Agent** | Evaluates a prospective purchase against wardrobe composition, style, and budget |
| **Wardrobe Optimization Agent** | Gap analysis, redundancy detection, cost-per-wear and usage analysis |
| **Fashion Inspiration Agent** | Contextual inspiration and discovery filtered by the user's style profile |
| **Conversational / Orchestrator Agent** | Natural-language entry point; routes requests to the right agent and synthesises responses |

The intent is **collaboration, not a monolithic model**. A single system asked to do vision, ranking, reasoning, and conversation at once tends to be weaker and harder to evaluate than specialised components with clear boundaries. Separating them also lets each capability be improved, measured, and replaced independently.

Concepts and technologies under consideration include:

- **Computer Vision** — garment detection, classification, instance segmentation, background removal, attribute (colour / material / pattern) extraction
- **Recommendation systems** — content-based and hybrid ranking over wardrobe embeddings; compatibility and compatibility scoring
- **LLM-based agents** — reasoning, explanation, and conversational interaction over wardrobe data
- **RAG** — retrieval over contextual fashion and wardrobe knowledge where it adds value
- **Weather and context APIs** — current conditions and forecasts as recommendation inputs
- **User preference and wardrobe history** — style profile, wear logs, cost-per-wear, saved outfits as the personal signal
- **Agent orchestration** — routing, tool access, shared memory, and fallback behaviour between agents

> **This architecture is not finalized.** The agent boundaries, model choices, orchestration framework, data stores, and evaluation strategy are all still being evaluated. The table above describes a direction of travel, not a committed design.

---

## Prototype

This repository contains the DressMe **UI / Figma prototype**, built as a React + Vite + Tailwind application from the Figma Make design. It exists to make the product tangible and testable before the technical implementation is decided.

The prototype is used to:

- **Validate the user experience** — test whether the flows are understandable and worth building.
- **Visualise the features** — show what each of the 7 business objectives looks like as an interface.
- **Define navigation and application flows** — settle the information architecture before a backend constrains it.
- **Demonstrate the 7 BOs** — give concrete form to each objective.
- **Provide a foundation for the technical implementation** — act as the visual and UX reference the real frontend is built against.

The prototype is interactive but **not connected to any backend, AI model, or data source**. Scores, weather, wardrobe items, recommendations, and chat replies are all hard-coded sample data for illustration. The prototype will keep evolving as product and technical decisions are refined.

### Prototype screens

The current prototype includes these sections:

| Section | Purpose | Related BO |
| --- | --- | --- |
| **Dashboard** | Daily AI recommendation, compatibility score, wardrobe stats, gap and duplicate analysis | BO2, BO5 |
| **My Wardrobe** | Item grid with search, category filters, sort by recency / wear / cost-per-wear, add-item flow | BO1, BO5 |
| **Outfit Studio** | Drag-and-drop outfit canvas with live style synergy scoring and suggested additions | BO2 |
| **Help Me Pack** | Trip form → generated pack list with own / buy / optional states and daily looks | BO3 |
| **Weather & Style** | 7-day forecast with per-day styling guidance from the user's own wardrobe | BO2, BO3 |
| **Should I Buy?** | Retail screenshot / URL analysis with purchase score, redundancy risk, and verdict | BO4 |
| **Find Similar** | Image reference → similar items with match percentages | BO7, BO4 |
| **AI Stylist** | Conversational interface with an active-context panel (weather, occasion, style, wardrobe size) | BO2, BO7 |
| **Style Profile** | Aesthetic affinities, colour palette, preferred occasions, size profile | BO1, BO7 |
| **Settings** | Account, regional preferences (currency, units, size system), AI and notification toggles | — |

---

## Screens

### Dashboard

![DressMe Dashboard](dashboard.png)

*Daily AI recommendation with compatibility score, wardrobe statistics, wardrobe gap analysis, and potential duplicate detection.*

### My Wardrobe

![DressMe Wardrobe](wardrobe.png)

*Structured wardrobe grid with search, category filtering, wear counts, and cost-per-wear per item.*

### Help Me Pack

![DressMe Help Me Pack](helpmepack.png)

*Trip intake and generated pack list, distinguishing items already owned, recommended purchases, and optional additions.*

---

## Current Status

**Done / in progress**

- Product ideation completed around the 7 business objectives.
- UI/UX prototype under development from the Figma design.
- Core navigation and the main feature flows implemented as interactive prototype screens.

**Still open**

- The technical architecture is not yet defined.
- The multi-agent approach is planned but not finalized — agent boundaries, models, and orchestration are unresolved.
- Feature scope, CV models, external APIs, data model, and implementation choices remain under evaluation.
- No AI pipeline, backend, or persistence layer exists yet.

**This is not a finished or production-ready product.**

---

## Roadmap

Indicative only — the order and content may change as decisions are made.

1. **UI / Figma prototype** — *(current)*
2. **UX validation and refinement** — user testing, flow fixes, design system consolidation
3. **Frontend implementation** — production app, real routing, state management, API layer
4. **Backend and data architecture** — wardrobe/item schema, user accounts, wear logs, storage for images
5. **Wardrobe computer vision pipeline** — detection, segmentation, background removal, classification, attribute extraction
6. **Recommendation and contextual intelligence** — compatibility scoring, occasion/weather conditioning, ranking
7. **Multi-agent architecture integration** — agent definitions, orchestration, shared memory, RAG where relevant
8. **Testing and evaluation** — CV accuracy, recommendation quality, agent task evaluation, user studies
9. **Iterative refinement** — feedback-driven improvement across the pipeline

---

## Repository Structure

The structure below is **indicative and will change** as the prototype transitions into the full application:

```text
DressMe/
├── UI / prototype/   # Current Figma-derived prototype (this repository today)
├── frontend/         # Production frontend (planned)
├── backend/          # Services, APIs, persistence (planned)
├── ai/               # Vision pipeline, agents, orchestration (planned)
└── docs/             # Product, architecture, and evaluation notes (planned)
```

Today the repository holds the prototype application and screenshots:

```text
DressMe/
├── README.md
├── dashboard.png
├── wardrobe.png
├── helpmepack.png
└── DressMe UI Blueprint/          # React + Vite + Tailwind prototype
    ├── index.html
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    └── src/
        ├── main.tsx
        ├── App.tsx                # All prototype screens and navigation
        └── index.css
```

### Running the prototype

```bash
cd "DressMe UI Blueprint"
pnpm install
pnpm dev
```

Requires Node.js and pnpm (versions pinned in `.mise.toml`).

---

## Disclaimer / Project Status

DressMe is **under active development**. The prototype, architecture, AI components, and feature scope may change as the project progresses. The seven business objectives and the multi-agent direction described above represent the current understanding of the product and are subject to revision — they should not be read as committed technical decisions or as evidence of implemented functionality.