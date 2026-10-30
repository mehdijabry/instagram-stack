"""Shared library for the Instagram Stack bundle.

Two lineages meet here. The publishing and reading layer comes from
sergebulaev/instagram-skills; the hook, slop and rubric tables come from
Jakeschincariol/instagram-agent-skill, where they were locked inside individual
skills. See NOTICE for what came from where.

One thing is new to this bundle: `approval` enforces the publish gate instead of
describing it. Nothing reaches a third party without a live, payload-bound
approval, and the bundle is read-only until it is armed from the launch
environment.
"""
from ._env import load_env

# Load .env before any client reads os.environ. Note that the arming flag
# INSTAGRAM_STACK_ALLOW_PUBLISH is deliberately absent from the .env allow-list:
# a repo that arrives with a clone must not be able to arm itself.
load_env()

from .url_parser import parse_instagram_url
from .publora_client import PubloraClient, PubloraError
from .pixfaro_client import PixfaroClient, PixfaroError
from .apify_client import ApifyClient, ApifyError, ApifyAuthError
from .approval import (
    ApprovalError,
    ApprovalRequired,
    PublishNotArmed,
    audit_trail,
    confirm,
    enforce,
    fingerprint,
    is_armed,
    render_approval_card,
)
from .corpus import (
    desloppify,
    hook_by_id,
    hook_ids,
    hook_rules,
    hooks,
    rubric,
    rubric_total,
    scan_slop,
    score_profile,
    slop,
    slop_total,
    strip_invisible,
)
from .backend_selector import (
    active_backend,
    available_models,
    illustrate,
    image_backend,
    manual_mode_message,
    publish,
    refine,
)

__all__ = [
    # publishing — gated
    "publish",
    "active_backend",
    "manual_mode_message",
    "PubloraClient",
    "PubloraError",
    # the gate itself
    "render_approval_card",
    "confirm",
    "enforce",
    "is_armed",
    "fingerprint",
    "audit_trail",
    "ApprovalError",
    "ApprovalRequired",
    "PublishNotArmed",
    # reading
    "parse_instagram_url",
    "ApifyClient",
    "ApifyError",
    "ApifyAuthError",
    # images
    "image_backend",
    "illustrate",
    "refine",
    "available_models",
    "PixfaroClient",
    "PixfaroError",
    # reference tables
    "hooks",
    "hook_rules",
    "hook_by_id",
    "hook_ids",
    "slop",
    "slop_total",
    "scan_slop",
    "desloppify",
    "strip_invisible",
    "rubric",
    "rubric_total",
    "score_profile",
]
