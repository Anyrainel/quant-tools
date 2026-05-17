# Quant-System Blueprint

**Version:** 1.1
**Last Updated:** 2026-05-16
**Owner:** ProClaw-Quant

This document is the single source of truth for the architecture of Vanilain's quant system. It describes the components, their interactions, data flows, and update responsibilities. **Any structural change to the system must be reflected here immediately.**

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         QUANT SYSTEM ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────┐  ┌──────────────────────────────┐        │
│  │     REPO 1: quant-principles │  │     REPO 2: quant-tools      │        │
│  │     (Wiki / Knowledge Base)    │  │     (Programmatic Inputs)    │        │
│  │                              │  │                              │        │
│  │  content/dalio/              │  │  gauge.py — macro regime     │        │
│  │  ├─ 01-09 chapters           │  │  broker.py — portfolio sync  │        │
│  │  ├─ atoms/ (270+)           │  │  rebalance.py — drift check  │        │
│  │  ├─ WIKI.md (schema)         │  │  backtest.py — simulation    │        │
│  │  └─ Quartz → Cloudflare      │  │  report.py — signal output   │        │
│  │                              │  │                              │        │
│  │  Rendered site:             │  │  Data outputs:              │        │
│  │  quant-principles.pages.dev  │  │  → scorecard.json           │        │
│  │                              │  │  → holdings.json            │        │
│  └──────────────┬───────────────┘  └──────────────┬───────────────┘        │
│                 │                                  │                          │
│                 └──────────────────┬───────────────┘                          │
│                                    ▼                                         │
│                          ┌─────────────────┐                               │
│                          │  GUIDANCE ENGINE │                               │
│                          │  (ProClaw-Quant)  │                               │
│                          │                  │                               │
│                          │  Reads: wiki +    │                               │
│                          │  signal outputs   │                               │
│                          │  → produces       │                               │
│                          │  recommendations  │                               │
│                          └────────┬─────────┘                               │
│                                   │                                          │
│                                   ▼                                          │
│                          ┌─────────────────┐                               │
│                          │    PORTFOLIO     │                               │
│                          │  (Vanilain's $)  │                               │
│                          └─────────────────┘                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Two-Repo Architecture

### Repo 1: `quant-principles` — Wiki / Knowledge Base
**URL:** https://github.com/Anyrainel/quant-principles  
**Rendered:** https://quant-principles.pages.dev

**Contents:**
- `content/dalio/` — 9 chapters organized in 4 phases: Mechanics → Calibration → Diagnostic → Action
- `content/dalio/atoms/` — 270+ atomic ideas with verbatim quotes and citations
- `sources/dalio/WIKI.md` — Schema, rubrics, and pipeline contract
- Quartz static site → Cloudflare Pages

**What goes here:**
- Wiki content (atoms, chapters, indices)
- Schema definitions (WIKI.md)
- Build reports and logs
- Quartz configuration

**What does NOT go here:**
- Python tooling (gauge, broker, etc.)
- Portfolio data
- API keys or credentials

---

### Repo 2: `quant-tools` — Programmatic Inputs
**URL:** https://github.com/Anyrainel/quant-tools

**Contents:**
- `gauge.py` — Macro regime classification (16 indicators, Dalio-style: debt cycle, stress, inflation)
- `broker.py` — Read-only portfolio sync from Robinhood + E*TRADE
- `rebalance.py` — Allocation drift detection + trade sizing
- `backtest.py` / `backtest_full.py` — Strategy simulation over historical regimes
- `timeline.py` — Historical macro data compilation
- `report.py` — Structured signal output for guidance engine
- Supporting: `allweather.py`, `alpha.py`, `debate.py`, `journal.py`, `monitor.py`, `portfolio.py`, `cache.py`
- Config: `allocations.yaml`, `config.yaml`, `rules.yaml`
- `data/` — Runtime outputs (scorecard.json, holdings.json, .env for secrets)
- `history/` — Archived scorecards

**What goes here:**
- All Python tooling
- Configuration files
- Runtime data outputs (not committed)

**What does NOT go here:**
- Wiki content
- Large historical datasets (use FRED/YFinance APIs)
- Secrets (stored in `data/.env`, gitignored)

---

## Data Flows

### Flow 1: Signal Generation (quant-tools)
```
[FRED API] ──┐
[YFinance] ──┼──→ gauge.py ──→ data/scorecard.json
[Brokers] ───┘      ↑
               broker.py ──→ data/holdings.json
```

### Flow 2: Guidance Generation (ProClaw-Quant)
```
quant-principles/content/dalio/ (principles)
         ↓
data/scorecard.json (current regime)
         ↓
data/holdings.json (portfolio snapshot)
         ↓
[Guidance Engine] → memory/YYYY-MM-DD.md (recommendations)
```

### Flow 3: Wiki Update (quant-principles)
```
New Source → [Atomize → Cluster → Route → Synthesize → Lint]
                                              ↓
                                       content/dalio/
                                              ↓
                                    REPORT.md + log.md
```

---

## File Inventory

### Core System Files (workspace root)
| File | Purpose | Update Owner |
|------|---------|-------------|
| `BLUEPRINT.md` (this file) | System architecture | ProClaw-Quant |
| `IDENTITY.md` | Agent identity + responsibilities | ProClaw-Quant |
| `SOUL.md` | Agent temperament + boundaries | ProClaw-Quant |
| `AGENTS.md` | Workspace rules + memory protocol | ProClaw-Quant |

### quant-principles (Wiki)
| File | Purpose | Update Owner |
|------|---------|-------------|
| `content/dalio/` | Wiki content (9 chapters) | Sub-agents per WIKI.md |
| `sources/dalio/WIKI.md` | Schema + pipeline contract | Human + ProClaw-Quant |
| `content/dalio/REPORT.md` | Build report + scores | Sub-agents |
| `content/dalio/log.md` | Ops log | Sub-agents |

### quant-tools (Programmatic)
| File | Purpose | Update Owner |
|------|---------|-------------|
| `gauge.py` | Macro regime classification | ProClaw-Quant |
| `broker.py` | Portfolio sync (RH + E*TRADE) | ProClaw-Quant |
| `rebalance.py` | Drift detection + sizing | ProClaw-Quant |
| `report.py` | Signal output formatting | ProClaw-Quant |
| `allocations.yaml` | Target allocation config | Vanilain |
| `config.yaml` / `rules.yaml` | Gauge config | ProClaw-Quant |
| `data/scorecard.json` | Latest regime reading | Auto-generated |
| `data/holdings.json` | Portfolio snapshot | Auto-generated |

### Memory Files
| File | Purpose | Update Owner |
|------|---------|-------------|
| `memory/YYYY-MM-DD.md` | Daily logs, signals, decisions | ProClaw-Quant |
| `MEMORY.md` | Curated long-term memory | ProClaw-Quant |

---

## Update Responsibilities

### ProClaw-Quant Must Update This Blueprint When:
- [ ] New repo is added or removed
- [ ] File locations or naming conventions change
- [ ] New component joins the system
- [ ] Data flows change

### Update Process:
1. Make the structural change
2. Immediately update `BLUEPRINT.md` to reflect it
3. Log the change in `memory/YYYY-MM-DD.md`
4. If identity/responsibilities change, update `IDENTITY.md`

---

## Current Status

### ✅ Working
- **quant-principles**: 9 chapters, 270+ atoms, Dalio sources ingested, deployed to Cloudflare
- **quant-tools**: All tooling extracted to dedicated repo, committed and pushed
- **Cross-agent comms**: ProClaw ↔ ProClaw-Quant verified

### 🔄 In Progress / Planned
- Signaling systems: gauge.py functional but needs regular run cadence
- Automated guidance generation: Need to establish review schedule
- Additional wiki branches: Howard Marks, Reinhart & Rogoff, Ilmanen (future)

### ❓ Open Questions
- How often should gauge.py run? (daily? weekly?)
- Should we set up a cron/heartbeat to auto-run gauge + report?
- Do we want automated alerts when regime shifts?

---

## Changelog

- `2026-05-16` — v1.1. Split into two repos: `quant-principles` (wiki) and `quant-tools` (programmatic). Updated architecture diagram and file inventory.
- `2026-05-16` — v1.0. Initial blueprint created. Documented existing wiki, portfolio, and conceptual signaling architecture.