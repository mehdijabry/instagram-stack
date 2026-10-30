# Instagram Stack

Fifteen Instagram skills for Claude Code and Codex, merged from two MIT bundles,
with the one thing neither of them had: **a publish gate that is enforced rather
than documented.**

```
read your niche  →  write  →  show the draft  →  you approve  →  publish
                                                      ↑
                                        nothing passes this point
                                        without a live, payload-bound approval
```

---

## Why this exists

Two good bundles already exist, and this one takes from both.

[**sergebulaev/instagram-skills**](https://github.com/sergebulaev/instagram-skills)
is maintained, versioned and checked in CI. It closes the loop: it reads what is
working in your niche through Apify, writes, and publishes through Publora. Its
`_env.py` draws a trust boundary most projects never think to draw — a `.env`
may carry API keys but may never name a command to execute.

[**Jakeschincariol/instagram-agent-skill**](https://github.com/Jakeschincariol/instagram-agent-skill)
never connects to anything, and was pushed twice in forty-one seconds and left
alone. But it carries three reference tables that are the real work: 26 hook
formulas each with the trap that makes it fail, 199 anti-slop entries that come
with their replacements, and a 12-criterion profile rubric.

**The gap both share:** the approval step before publishing was a convention.
The upstream file said so in its own docstring — *"a thin conventions layer, not
runtime enforcement."* A skill that forgot the card could still reach Instagram,
and a draft that changed between the card and the call went out unapproved.

This bundle closes that gap, keeps everything else, and says exactly what came
from where in [NOTICE](NOTICE).

---

## The gate

Three locks, in `lib/approval.py`. `lib.publish()` calls `enforce()` before any
branch that reaches a third party.

| Lock | What it stops |
|---|---|
| **ARM** | The bundle is read-only until `INSTAGRAM_STACK_ALLOW_PUBLISH=1` is set **in the environment you launch from**. A `.env` cannot set it — same boundary `_env.py` already draws around executables. |
| **BINDING** | An approval is bound to a fingerprint of the exact payload shown. Approve caption A, publish caption B, and it fails. This is the lock that catches the realistic accident. |
| **FRESH** | Single use, expired after 15 minutes. An approval cannot be replayed onto a later post. |

Every attempt, allowed or refused, lands in `.instagram-stack/publish-audit.log`:

```
2026-10-30T16:24:01-0400  refused    post  79aff2c0…  never confirmed
2026-10-30T16:24:01-0400  refused    post  9150402e…  no approval for this exact draft
2026-10-30T16:24:01-0400  published  post  79aff2c0…  token 3adabf308e80
2026-10-30T16:24:02-0400  refused    post  79aff2c0…  already used
```

Six cases are proven in `tests/test_approval_gate.py`, and
`scripts/check_approval_lock.py` fails the build if a later edit lets
`publish()` step around the gate.

### What the gate does not do

An agent running arbitrary code in this process can call `confirm()` itself.
These locks stop **mistakes** — a skill that skips the card, a test that
publishes for real, a draft edited after approval. They are not a sandbox, and
nothing inside a Python process can be.

If an account matters enough that a hostile agent is in your threat model, keep
`PUBLORA_API_KEY` out of the environment entirely. The bundle then drafts and
you post by hand, which is also how it ships by default.

---

## Install

```bash
git clone https://github.com/mehdijabry/instagram-stack.git
cd instagram-stack
```

That is the whole install for the drafting half. No keys, no accounts, no
network. Point your agent at the folder and ask for a caption.

To let it read your niche or publish, copy `.env.example` to `.env` and fill in
only what you use. Then, deliberately, in the shell you launch from:

```bash
export INSTAGRAM_STACK_ALLOW_PUBLISH=1
```

Leave that line out until you have watched the approval card appear on a dozen
drafts. The bundle is useful without it.

---

## The fifteen skills

**Writing** — produce text and files, touch nothing else

| Skill | What it produces |
|---|---|
| `ig-caption-writer` | Caption with the hook in the first 125 characters, a skimmable body, one CTA |
| `ig-carousel-planner` | Up to 10 slides: hook slide that opens a loop, value slides, payoff slide |
| `ig-reel` | Reel script: hook options, spoken line, on-screen line, beat sheet |
| `ig-story` | Story sequence frame by frame, sticker placement, order across the day |
| `ig-repurposer` | A LinkedIn post, blog, YouTube script or X thread rebuilt as native Instagram |
| `ig-hashtag-strategist` | 3–5 sized tags (niche / mid / broad) a small account can actually rank in |

**Reading** — the only skills that leave your machine

| Skill | Reach |
|---|---|
| `ig-audience-insights` | Scans a hashtag and pulls profile stats through Apify. No login |
| `ig-hook-extractor` | Reverse-engineers the hook of a reel that worked, from a URL or a pasted caption |
| `ig-viral` | Finds what is travelling in your niche through the session's own browser, after you approve 6–12 accounts. Ranks by multiple of the account's baseline, not raw views |

**Judging** — read what you give them

| Skill | Reach |
|---|---|
| `ig-humanizer` | Strips the machine fingerprint using all 199 entries, then scores what is left |
| `ig-profile-optimizer` | Scores the profile out of 100 on 12 criteria, rewrites what loses points |
| `ig-audit` | Post-mortem on published posts, from statistics you paste |
| `ig-content-planner` | The week: what, which format, when, and who to engage. Schedules nothing |

**Interacting** — draft, you send

| Skill | Reach |
|---|---|
| `ig-comment` | Comments for other accounts' posts. Never auto-posts |
| `ig-reply` | Replies to your own comments, sorted by what is worth answering |

### Not included

`ig-dm` from upstream B. The skill is well written and its guardrails are sound.
It is left out because a bundle aimed at an account a business depends on should
not make direct-message prospecting easy to run at volume — that is the shortest
path to a restricted account. Fetch it from upstream if you disagree; it is MIT.

---

## The shared tables

What was locked inside single skills upstream is a library here.

```python
from lib import hooks, scan_slop, desloppify, score_profile

hooks()                      # 26 formulas, each with its documented trap
desloppify(draft)            # rewrite using the table's own replacements
scan_slop(draft)             # report only — the writer decides
score_profile({"bio": 8})    # out of 100, with the three biggest losses named
```

`desloppify` returns the rewritten text **and every change it made**. A humaniser
that edits silently is worse than one that does nothing. Structural entries —
*"it's not just X, it's Y"* — are reported, never auto-applied: deleting the
setup half is a judgement, not a substitution.

It removes a fingerprint. It does **not** make text undetectable, and no skill
here may tell a user that it does.

---

## Publishing backends

`lib.publish()` routes to whichever backend is configured.

| Backend | When | Notes |
|---|---|---|
| `manual` | Default, no keys | Prints the copy-paste block. Needs no approval and no arming — it publishes nothing |
| `publora` | `PUBLORA_API_KEY` + `INSTAGRAM_PLATFORM_ID` | Carried over from upstream A. A publishing API, not a bot driving the app |
| `diy` | `INSTAGRAM_SKILLS_CUSTOM_POSTER` | Your own command, JSON on stdin. Must come from the launch environment |

Publora is the backend upstream A wired in, and this bundle kept the client
because it works. The sign-up link here carries **no attribution parameters** —
upstream tagged it so sign-ups were credited to the bundle author. Compare it
against Buffer, Later, Metricool or the Instagram Graph API directly before you
hand any vendor your business account; the `diy` backend exists so you can use
something else without touching this code.

---

## Running the checks

```bash
python3 tests/test_approval_gate.py
python3 scripts/check_approval_lock.py
python3 scripts/check_no_secrets.py
python3 scripts/check_untrusted_rule.py
```

---

## Before you use this on an account that matters

**Fill the voice profile properly.** Both upstreams are calibrated on American
English. `references/voice-profile.md` is where a real business becomes
distinguishable from every other account using the same formulas: the words your
customers actually use, the objections they actually raise, and what you never
say. Skip it and the bundle produces generic content at speed, which is what
people already complain about.

**Nothing here is a growth guarantee.** These are hook formulas, a slop
dictionary and a publishing client. They shorten the part of the work that is
writing. They do not know your customers.

---

## Credit

The work is upstream. See [NOTICE](NOTICE) for what came from where, file by
file. Both projects are MIT; if you build on this, carry their names forward
too.
