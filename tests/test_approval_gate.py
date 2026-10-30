"""The gate, proven rather than described.

Six cases. Case 4 is the one that justifies the whole module: a draft approved
and then edited before publishing must not go out. Both upstream bundles would
have published it.

Run: python3 tests/test_approval_gate.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Fake values, local only. They exist so active_backend() picks the publora
# branch; no request is ever completed.
os.environ["PUBLORA_API_KEY"] = "sk_test_local_only"
os.environ["INSTAGRAM_PLATFORM_ID"] = "instagram-test"
os.environ["INSTAGRAM_STACK_HOME"] = tempfile.mkdtemp(prefix="ig-stack-test-")

PAYLOAD = {"media": ["example.jpg"]}
DRAFT = "The draft the user approved"
TARGET = "https://www.instagram.com/example/"

failures = []


def reload_lib():
    for name in [m for m in list(sys.modules) if m.startswith("lib")]:
        del sys.modules[name]
    import lib
    return lib


def check(label, fn, expect):
    try:
        fn()
        got = "allowed"
    except Exception as exc:  # noqa: BLE001 - the exception type is the result
        got = type(exc).__name__
    ok = (got == expect) or (expect == "allowed-or-provider" and got in ("allowed", "PubloraError"))
    print(f"  [{'ok' if ok else 'FAIL'}] {label}: {got}")
    if not ok:
        failures.append(f"{label}: expected {expect}, got {got}")


os.environ.pop("INSTAGRAM_STACK_ALLOW_PUBLISH", None)
lib = reload_lib()
assert lib.active_backend() == "publora", "test needs the publora branch"

print("approval gate")
check("unarmed bundle refuses", lambda: lib.publish("post", DRAFT, TARGET, **PAYLOAD), "PublishNotArmed")

os.environ["INSTAGRAM_STACK_ALLOW_PUBLISH"] = "1"
lib = reload_lib()

check("armed but no card rendered", lambda: lib.publish("post", DRAFT, TARGET, **PAYLOAD), "ApprovalRequired")

card = lib.render_approval_card(kind="post", preview_text=DRAFT, target_url=TARGET, **PAYLOAD)
token = card.split("**Approval token:** `")[1].split("`")[0]
check("card rendered, not confirmed", lambda: lib.publish("post", DRAFT, TARGET, **PAYLOAD), "ApprovalRequired")

lib.confirm(token)
check("confirmed, then the text changed",
      lambda: lib.publish("post", DRAFT + " (edited)", TARGET, **PAYLOAD), "ApprovalRequired")
check("confirmed, text unchanged",
      lambda: lib.publish("post", DRAFT, TARGET, **PAYLOAD), "allowed-or-provider")
check("token replayed", lambda: lib.publish("post", DRAFT, TARGET, **PAYLOAD), "ApprovalRequired")

trail = lib.audit_trail()
print(f"\naudit log: {len(trail)} entries")
if not any("published" in line for line in trail) or not any("refused" in line for line in trail):
    failures.append("audit log did not record both outcomes")

if failures:
    print("\nFAILED")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("\nall gate checks passed")
