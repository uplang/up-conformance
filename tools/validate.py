#!/usr/bin/env python3
"""Validate the corpus: every expect.json obeys its expectation contract
(README.md / schema/expect.schema.json for rung cases, schema/typing.expect.schema.json
for typing cases) and manifest.json matches the case directories exactly.
`--write` regenerates manifest.json from the case directories instead of
comparing. Pure stdlib so CI needs no dependencies. Exits non-zero on the
first class of failure, printing every finding."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ERROR_CODE = re.compile(r"^E_[A-Z_]+$")
TYPING_CODE = re.compile(r"^T_[A-Z_]+$")
LINT_CODE = re.compile(r"^W_[A-Z_]+$")
ALLOWED_KEYS = {"expect", "model", "code", "lint", "rung_exact", "provisional", "note", "error_contains"}
ALLOWED_TYPING_KEYS = {"expect", "model", "mode", "code", "line", "note"}


def check_case(path: Path, findings: list[str]) -> None:
    if not (path / "input.up").is_file():
        findings.append(f"{path}: missing input.up")
    expect_path = path / "expect.json"
    if not expect_path.is_file():
        findings.append(f"{path}: missing expect.json")
        return
    exp = json.loads(expect_path.read_text())
    check_expectation(path, exp, findings)


def check_expectation(path: Path, exp: dict, findings: list[str]) -> None:
    for key in exp:
        if key not in ALLOWED_KEYS:
            findings.append(f"{path}: unknown key {key!r}")
    provisional = exp.get("provisional", False)
    kind = exp.get("expect")
    if kind == "parse":
        if "model" not in exp and not provisional:
            findings.append(f"{path}: parse expectation without model")
        for code in exp.get("lint", []):
            if not LINT_CODE.match(code):
                findings.append(f"{path}: bad lint code {code!r}")
    elif kind == "error":
        code = exp.get("code")
        if code is None:
            if not provisional:
                findings.append(f"{path}: error expectation without code")
        elif not ERROR_CODE.match(code):
            findings.append(f"{path}: bad error code {code!r}")
    else:
        findings.append(f"{path}: expect must be parse or error, got {kind!r}")


def check_typing_case(path: Path, findings: list[str]) -> None:
    if not (path / "input.up").is_file():
        findings.append(f"{path}: missing input.up")
    exp = json.loads((path / "expect.json").read_text())
    for key in exp:
        if key not in ALLOWED_TYPING_KEYS:
            findings.append(f"{path}: unknown key {key!r}")
    check_typing_expectation(path, exp, findings)


def check_typing_expectation(path: Path, exp: dict, findings: list[str]) -> None:
    kind = exp.get("expect")
    if kind == "typed":
        if "model" not in exp:
            findings.append(f"{path}: typed expectation without model")
        if exp.get("mode") not in (None, "open"):
            findings.append(f"{path}: bad mode {exp.get('mode')!r}")
        if "line" in exp:
            findings.append(f"{path}: line is expect=error only")
    elif kind == "error":
        if not TYPING_CODE.match(exp.get("code", "")):
            findings.append(f"{path}: bad typing code {exp.get('code')!r}")
        check_line(path, exp, findings)
    else:
        findings.append(f"{path}: typing expect must be typed or error, got {kind!r}")


def check_line(path: Path, exp: dict, findings: list[str]) -> None:
    line = exp.get("line")
    if line is not None and (not isinstance(line, int) or isinstance(line, bool) or line < 1):
        findings.append(f"{path}: line must be a positive integer, got {line!r}")


def built_manifest_rungs(old: dict) -> list[dict]:
    titles = {r["rung"]: (r["title"], r.get("provisional", False)) for r in old["rungs"]}
    rungs = []
    for rung_dir in sorted((ROOT / "rungs").iterdir(), key=lambda p: int(p.name)):
        cases = [rung_case_entry(case_dir) for case_dir in sorted((rung_dir / "cases").iterdir())]
        title, prov = titles[int(rung_dir.name)]
        rungs.append({"rung": int(rung_dir.name), "title": title, "provisional": prov, "count": len(cases), "cases": cases})
    return rungs


def rung_case_entry(case_dir: Path) -> dict:
    exp = json.loads((case_dir / "expect.json").read_text())
    entry = {"name": case_dir.name, "expect": exp["expect"]}
    if "code" in exp:
        entry["code"] = exp["code"]
    if exp.get("lint"):
        entry["lint"] = exp["lint"]
    if exp.get("rung_exact"):
        entry["rung_exact"] = True
    if exp.get("provisional"):
        entry["provisional"] = True
    return entry


def built_manifest_typing() -> dict:
    cases = [typing_case_entry(case_dir) for case_dir in sorted((ROOT / "typing" / "cases").iterdir())]
    return {"layout": "typing/cases/<name>/{input.up, expect.json}", "schema": "schema/typing.expect.schema.json", "count": len(cases), "cases": cases}


def typing_case_entry(case_dir: Path) -> dict:
    exp = json.loads((case_dir / "expect.json").read_text())
    entry = {"name": case_dir.name, "expect": exp["expect"]}
    if "code" in exp:
        entry["code"] = exp["code"]
    if "mode" in exp:
        entry["mode"] = exp["mode"]
    return entry


def write_manifest(manifest: dict) -> None:
    manifest["rungs"] = built_manifest_rungs(manifest)
    manifest["typing"] = built_manifest_typing()
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def check_manifest(manifest: dict, findings: list[str]) -> None:
    if manifest["rungs"] != built_manifest_rungs(manifest):
        findings.append("manifest.json rungs are stale — regenerate with tools/validate.py --write")
    if manifest.get("typing") != built_manifest_typing():
        findings.append("manifest.json typing index is stale — regenerate with tools/validate.py --write")


def main() -> int:
    findings: list[str] = []
    for rung_dir in sorted((ROOT / "rungs").iterdir()):
        for case_dir in sorted((rung_dir / "cases").iterdir()):
            check_case(case_dir, findings)
    for case_dir in sorted((ROOT / "typing" / "cases").iterdir()):
        check_typing_case(case_dir, findings)
    manifest = json.loads((ROOT / "manifest.json").read_text())
    if "--write" in sys.argv[1:]:
        write_manifest(manifest)
    else:
        check_manifest(manifest, findings)
    for f in findings:
        print(f"FAIL: {f}")
    if not findings:
        total = sum(r["count"] for r in manifest["rungs"])
        typing_total = len(list((ROOT / "typing" / "cases").iterdir()))
        print(f"ok: {total} parse cases + {typing_total} typing cases valid, manifest current")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
