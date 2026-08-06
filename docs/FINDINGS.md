# Findings and Learnings — Hodi

Daily observations, crawler log metrics, Gemma triage rate, scope lattice edge cases, and Google-toolchain findings (Antigravity & OTel).

---

### 2026-08-06 — Canary Planting & Corpus Ownership Verification (HOD-009, HOD-105)

**Canary Plant Date:** `2026-08-06T12:40:00Z`

**Planted Canary Strings:**
1. `HODI-CANARY-20260806-PROSE-9F81A2B3C4` (Medium Essays & Technical Writing)
2. `HODI-CANARY-20260806-CODE-7639226A1B` (Public GitHub Repository `Jeremiah-Sakuda/Hodi`)
3. `HODI-CANARY-20260806-AUDIO-4C5D6E7F8A` (Electric Bass Solo Recordings & Stems)
4. `HODI-CANARY-20260806-PROSE-DRAFT-1A2B3C` (Draft Notes on Multi-Agent Consent)
5. `HODI-CANARY-20260806-AUDIO-LIVE-3C4D5E` (Live Bass Improvisation Session)

**Explicit Limitation & Boundaries:**
- **Temporal Bound:** Canary strings only protect items published *after* the planting date (`2026-08-06T12:40:00Z`).
- **No Retroactive Coverage:** Canaries cannot detect scrapes or training ingest that occurred prior to planting. Hodi structurally enforces this boundary and makes no claim of retroactive detection for pre-existing corpus access.
- **Proof-of-Control Enforcement (HOD-105):** All 3 works at `verified_control` carry stored `control_proof` records (`well_known_file`, `signed_commit`, `platform_oauth`). Two works (`work-essay-002`, `work-audio-002`) are deliberately registered at `asserted` with `control_proof = None` to ensure all 3 control tiers are available for console and API rendering from real corpus data.
