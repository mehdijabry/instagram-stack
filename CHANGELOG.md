# Changelog

## 1.0.0 — 30 October 2026

First release. A merge of two MIT bundles, plus one thing neither had.

### Added
- **`lib/approval.py` — the publish gate, enforced.** Both upstreams shipped an
  approval card as a convention; the upstream file said so itself. Here
  `lib.publish()` calls `enforce()` before any branch that reaches a provider.
  Three locks: arming from the launch environment only, approval bound to a
  fingerprint of the exact payload, single use with a 15-minute expiry. Every
  attempt is written to `.instagram-stack/publish-audit.log`.
- **`lib/corpus.py` — the reference tables as a library.** The 26 hook formulas,
  199 anti-slop entries and 12-criterion rubric sat inside single skills
  upstream. `desloppify()` applies the table's own replacements and returns
  every change it made; structural entries are reported, never auto-applied.
- `tests/test_approval_gate.py` — six cases, including the one that matters: a
  draft approved and then edited must not publish.
- `scripts/check_approval_lock.py` — fails the build if a later edit lets
  `publish()` step around the gate, or if the arming flag becomes loadable from
  a `.env`.

### Changed
- `lib/backend_selector.py` — the Publora sign-up link no longer carries the
  `utm_source` / `utm_medium` / `utm_campaign` parameters that attributed
  sign-ups to the upstream author. The link still works.
- Hook, slop and rubric data moved to `data/`; every skill and script that
  referenced them in their old per-skill locations was repointed.

### Not carried over
- `ig-dm` from Jakeschincariol/instagram-agent-skill. Well written, sound
  guardrails, deliberately excluded: a bundle aimed at an account a business
  depends on should not make DM prospecting easy to run at volume.

### Corrected from the upstream README
- Upstream B's README describes its hook table as 26 scored formulas, which is
  accurate: `data/hooks.json` holds 26. Any count of 58 refers to the `phrases`
  class inside `slop.json`, not to hooks.
