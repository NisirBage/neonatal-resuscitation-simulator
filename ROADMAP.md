# Roadmap

This document outlines potential future directions for the Neonatal Resuscitation Simulator.
Items are listed in rough priority order and are subject to change.

> **Note:** This is an academic project. Contributions are welcome but must not alter
> the clinical accuracy of the NRP workflow without subject-matter expert review.

---

## Near-term (v1.1)

- [ ] **Additional scenarios** — APGAR scoring, meconium-stained amniotic fluid, premature infant pathways
- [ ] **Multi-language voice support** — Welsh, French, Spanish prompt sets
- [ ] **Student authentication** — JWT-gated student endpoints so sessions are tied to a user account
- [ ] **Session history list** — instructors can browse past completed sessions

## Medium-term (v1.2)

- [ ] **Competency tracking** — aggregate multiple sessions to track student progress over time
- [ ] **Instructor annotations** — instructors can attach text notes to replay events
- [ ] **SCORM export** — package session data for LMS integration (Moodle, Canvas)
- [ ] **PostgreSQL as default** — migrate from SQLite to PostgreSQL for multi-instance deployments

## Long-term (v2.0)

- [ ] **Audio transcription** — Whisper-based voice-to-text as an alternative to Web Speech API for wider browser support
- [ ] **Video overlay** — optional webcam feed recorded alongside the simulation for debriefing
- [ ] **Branching scenarios** — scenarios with non-linear paths that adapt based on cumulative performance
- [ ] **Mobile PWA** — offline-capable progressive web app for tablet use in simulation centres

## Out of scope

The following are explicitly **not** planned for this codebase:

- Patient data storage (this is a training tool, not a clinical record system)
- Real-time multiplayer (multi-student sessions sharing a single simulation)
- Integration with physical simulation manikins
