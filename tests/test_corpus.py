"""The shared tables: counts, and that the rewriter does what it claims.

Run: python3 tests/test_corpus.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import corpus  # noqa: E402

failures = []


def check(label, got, expect):
    ok = got == expect
    print(f"  [{'ok' if ok else 'FAIL'}] {label}: {got}")
    if not ok:
        failures.append(f"{label}: expected {expect}, got {got}")


def check_true(label, got):
    print(f"  [{'ok' if got else 'FAIL'}] {label}")
    if not got:
        failures.append(label)


print("counts")
check("hook formulas", len(corpus.hooks()), 26)
check("hook rules", len(corpus.hook_rules()), 6)
check("slop entries, all classes", corpus.slop_total(), 199)
check("rubric criteria", len(corpus.rubric()), 12)
check("rubric total", corpus.rubric_total(), 100)
check_true("every hook has an id", all(h.get("id") for h in corpus.hooks()))
check_true("classify_order matches the hooks",
           set(corpus.hook_ids()) == {h["id"] for h in corpus.hooks()})

print("\ninvisible characters")
dirty = "clean​text­here\U000e0041"
clean, removed = corpus.strip_invisible(dirty)
check("removed", removed, 3)
check("result", clean, "cleantexthere")
check("a clean string is untouched", corpus.strip_invisible("plain text"), ("plain text", 0))

print("\nscan reports, never edits")
draft = "In today's fast-paced world, let us delve into this seamless journey."
found = corpus.scan_slop(draft)
check_true("finds the opener phrase", any(f["class"] == "phrases" for f in found))
check_true("every finding carries a replacement",
           all("suggest" in f for f in found))
check_true("scan leaves the draft alone", draft == "In today's fast-paced world, let us delve into this seamless journey.")

print("\nrewrite reports every change")
out, changes = corpus.desloppify(draft)
check_true("the opener is gone", "fast-paced world" not in out)
check_true("something changed", bool(changes))
check_true("each change names from and to",
           all({"from", "to", "class"} <= set(c) for c in changes))
check_true("capitalisation is preserved at the sentence start", out[0].isupper())
check_true("no double spaces left behind", "  " not in out)

print("\nstructural tells are reported, not applied")
structural = "It's not just a tool, it's a revolution."
out2, changes2 = corpus.desloppify(structural)
check_true("the structure survives the rewrite", "not just a tool" in out2)
check_true("but it is reported",
           any(c["class"] == "structures" for c in changes2))

print("\nprofile scoring")
result = corpus.score_profile({"name_field": 12})
check("score", result["score"], 12)
check("criteria", result["criteria"], 12)
check_true("names the biggest losses", len(result["biggest_losses"]) == 3)
check_true("an unassessed criterion scores zero", result["assessed"] == 1)
check("points are clamped to the maximum",
      corpus.score_profile({"name_field": 999})["score"], 12)

if failures:
    print("\nFAILED")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("\nall corpus checks passed")
