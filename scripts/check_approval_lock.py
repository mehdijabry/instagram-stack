"""CI guard: the publish path must stay behind the gate.

The gate is only worth having if a later edit cannot quietly step around it.
This check fails the build when `publish()` can reach a third party without
calling `approval.enforce()` first, and when the arming flag becomes loadable
from a .env.

Run: python3 scripts/check_approval_lock.py
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SELECTOR = ROOT / "lib" / "backend_selector.py"
ENV = ROOT / "lib" / "_env.py"
ARM_FLAG = "INSTAGRAM_STACK_ALLOW_PUBLISH"

problems: list[str] = []
source = SELECTOR.read_text(encoding="utf-8")
tree = ast.parse(source)

publish = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "publish"), None)
if publish is None:
    problems.append("lib/backend_selector.py no longer defines publish()")
else:
    enforce_line = None
    for node in ast.walk(publish):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "enforce"):
            enforce_line = node.lineno
            break
    if enforce_line is None:
        problems.append("publish() does not call approval.enforce()")
    else:
        # Every branch that reaches a provider must sit after the gate.
        for marker in ('if backend == "publora":', 'if backend == "diy":'):
            idx = source.find(marker)
            if idx == -1:
                continue
            branch_line = source[:idx].count("\n") + 1
            if branch_line < enforce_line:
                problems.append(
                    f"the {marker.strip()} branch (line {branch_line}) runs before "
                    f"approval.enforce() (line {enforce_line})"
                )

env_source = ENV.read_text(encoding="utf-8")
allow_list = env_source.split("_DOTENV_VARIABLES")[1] if "_DOTENV_VARIABLES" in env_source else ""
if ARM_FLAG in allow_list.split(")")[0]:
    problems.append(f"{ARM_FLAG} must never be loadable from a .env file")

if problems:
    print("approval lock check: FAILED")
    for p in problems:
        print(" -", p)
    sys.exit(1)
print("approval lock check: ok (publish() is gated, arming stays out of .env)")
