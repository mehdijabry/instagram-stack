"""Approval gate — enforced at runtime, not merely documented.

The bundle this file replaces shipped an approval card and said so plainly:
"This file is a thin conventions layer, not runtime enforcement." A skill that
forgot to render the card could still reach Instagram. This module closes that
gap: `lib.publish()` calls `enforce()` first, and `enforce()` refuses unless the
exact payload in front of it carries a live approval.

Three independent locks
-----------------------
1. ARM      The bundle is read-only until INSTAGRAM_STACK_ALLOW_PUBLISH=1 is
            set in the LAUNCH environment. A .env file cannot set it — same
            trust boundary `_env.py` already draws around executables.
2. BINDING  An approval is tied to a fingerprint of the exact payload that was
            shown. Approve caption A, try to publish caption B, and it fails.
            This is the lock that catches the realistic accident: the draft
            mutating between the card and the call.
3. FRESH    Single use, and expired after APPROVAL_TTL seconds. An approval
            cannot be replayed on a later post.

Every attempt, allowed or refused, is appended to the audit log.

What this does NOT defend against
---------------------------------
An agent running arbitrary code in this process can call `confirm()` itself, or
reassign this module. These locks stop mistakes — a skill that skips the card, a
test that publishes for real, a draft that changed after approval. They are not
a sandbox, and nothing in a Python process can be. If an account matters enough
that a hostile agent is in the threat model, keep PUBLORA_API_KEY out of the
environment entirely and publish by hand.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

APPROVAL_TTL = int(os.environ.get("INSTAGRAM_STACK_APPROVAL_TTL", "900"))

#: Captured at import, from the launch environment only. `_env.py` refuses to
#: load this name out of a .env, so a cloned repo cannot arm itself.
_ARMED_AT_IMPORT = os.environ.get("INSTAGRAM_STACK_ALLOW_PUBLISH", "").strip() == "1"

_AUDIT_DIR = Path(os.environ.get("INSTAGRAM_STACK_HOME", ".instagram-stack"))
_AUDIT_LOG = _AUDIT_DIR / "publish-audit.log"

_PENDING: dict[str, "Approval"] = {}


class ApprovalError(RuntimeError):
    """Base class for every refusal raised by this module."""


class PublishNotArmed(ApprovalError):
    """Publishing is disabled because the bundle was not armed at launch."""


class ApprovalRequired(ApprovalError):
    """No live approval matches the payload being published."""


@dataclass
class Approval:
    """One approval, bound to one payload."""

    token: str
    fingerprint: str
    kind: str
    issued_at: float
    confirmed: bool = False
    used: bool = False
    card: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def expired(self) -> bool:
        return (time.time() - self.issued_at) > APPROVAL_TTL

    @property
    def live(self) -> bool:
        return self.confirmed and not self.used and not self.expired


# --------------------------------------------------------------------------
# fingerprinting
# --------------------------------------------------------------------------

#: Only the fields that change what a reader sees are fingerprinted. Scheduling
#: a post an hour later is not a different post; changing one word is.
_BOUND_FIELDS = ("media", "media_urls", "platforms", "platform_id")


def fingerprint(kind: str, draft_text: str, target_url: str, **kwargs: Any) -> str:
    """Return a stable hash of what a reader would actually receive."""
    payload = {
        "kind": kind,
        "draft_text": draft_text,
        "target_url": target_url,
    }
    for name in _BOUND_FIELDS:
        value = kwargs.get(name)
        if value:
            payload[name] = sorted(value) if isinstance(value, list) else value
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------------------
# the card
# --------------------------------------------------------------------------


def render_approval_card(
    *,
    kind: str,
    preview_text: str,
    target_url: Optional[str] = None,
    char_count: Optional[int] = None,
    slide_count: Optional[int] = None,
    media_note: Optional[str] = None,
    extra_context: Optional[dict] = None,
    **payload: Any,
) -> str:
    """Format the draft for review AND register a pending approval for it.

    Signature-compatible with the upstream helper, so every skill carried over
    keeps working. The difference is the side effect: rendering a card is now
    what mints the token `confirm()` needs, and the token is bound to this exact
    draft. The card ends with the token so the user sees what they are approving.
    """
    target = target_url or ""
    fp = fingerprint(kind, preview_text, target, **payload)
    token = hashlib.sha256(f"{fp}:{time.time()}".encode()).hexdigest()[:12]

    if char_count is None:
        char_count = len(preview_text)
    fold = " (first ~125 show before the 'more' fold)" if char_count > 125 else ""

    lines = [f"## Draft ready for approval — {kind}", ""]
    if target_url:
        lines.append(f"**Target:** {target_url}")
    lines.append(f"**Caption chars:** {char_count} / 2200{fold}")
    if slide_count is not None:
        lines.append(f"**Slides:** {slide_count}")
    if media_note:
        lines.append(f"**Media you supply:** {media_note}")
    lines += ["", "**Caption preview:**", ""]
    for pl in preview_text.splitlines() or [""]:
        lines.append(f"> {pl}")
    lines.append("")
    if extra_context:
        lines.append("**Context:**")
        for k, v in extra_context.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")

    if not is_armed():
        lines += [
            "> **Publishing is not armed.** This bundle cannot reach Instagram "
            "until `INSTAGRAM_STACK_ALLOW_PUBLISH=1` is set in the environment "
            "you launch the agent from. Until then, approving prints the "
            "copy-paste block instead.",
            "",
        ]

    lines += [
        f"**Approval token:** `{token}`  ·  expires in {APPROVAL_TTL // 60} min",
        "",
        "Reply **post** / **yes** to publish, or suggest edits. "
        "Any edit voids this token and issues a new card.",
    ]

    card = "\n".join(lines)
    _PENDING[token] = Approval(
        token=token,
        fingerprint=fp,
        kind=kind,
        issued_at=time.time(),
        card=card,
        context={"target_url": target, "chars": char_count},
    )
    return card


# --------------------------------------------------------------------------
# the gate
# --------------------------------------------------------------------------


def is_armed() -> bool:
    """True when publishing was enabled from the launch environment."""
    return _ARMED_AT_IMPORT


def confirm(token: str) -> Approval:
    """Record the user's yes for one pending card."""
    approval = _PENDING.get(token)
    if approval is None:
        raise ApprovalRequired(
            f"No pending approval for token {token!r}. Render the card again — "
            "tokens do not survive a restart, by design."
        )
    if approval.expired:
        raise ApprovalRequired(
            f"Token {token!r} expired after {APPROVAL_TTL}s. Render a fresh card."
        )
    approval.confirmed = True
    return approval


def enforce(kind: str, draft_text: str, target_url: str, **kwargs: Any) -> Approval:
    """Gate one publish call. Raises unless a live approval binds this payload.

    Called by `lib.publish()` before any backend is reached. Every outcome is
    written to the audit log, refusals included.
    """
    fp = fingerprint(kind, draft_text, target_url, **kwargs)

    if not is_armed():
        _audit("refused", fp, kind, "not armed")
        raise PublishNotArmed(
            "Publishing is disabled. Set INSTAGRAM_STACK_ALLOW_PUBLISH=1 in the "
            "environment you launch from — a .env cannot set it. Until then the "
            "bundle drafts and you post by hand."
        )

    for approval in _PENDING.values():
        if approval.fingerprint == fp and approval.live:
            approval.used = True
            _audit("published", fp, kind, f"token {approval.token}")
            return approval

    stale = [a for a in _PENDING.values() if a.fingerprint == fp]
    if stale:
        why = "already used" if any(a.used for a in stale) else (
            "expired" if any(a.expired for a in stale) else "never confirmed"
        )
        _audit("refused", fp, kind, why)
        raise ApprovalRequired(
            f"The approval for this draft is {why}. Render a fresh card and "
            "confirm it before publishing."
        )

    _audit("refused", fp, kind, "no approval for this exact draft")
    raise ApprovalRequired(
        "This draft was never approved. If you approved an earlier version, the "
        "text changed since — that is what this check exists to catch. Render "
        "the card for the current draft and confirm it."
    )


# --------------------------------------------------------------------------
# audit trail
# --------------------------------------------------------------------------


def _audit(outcome: str, fp: str, kind: str, note: str) -> None:
    """Append one line per attempt. Never raises: a failing log must not
    become a reason a refusal is skipped."""
    try:
        _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with _AUDIT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp}\t{outcome}\t{kind}\t{fp}\t{note}\n")
    except OSError:
        pass


def audit_trail(limit: int = 20) -> list[str]:
    """Return the most recent audit lines, newest last."""
    try:
        return _AUDIT_LOG.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []


def reset_for_tests() -> None:
    """Drop every pending approval. Test helper, not for skills."""
    _PENDING.clear()
