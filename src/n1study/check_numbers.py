"""Fail if a document quotes a number that no file in results/ contains.

Every number token in the prose is matched against every number in results/*.csv,
results/*.json and the study settings in config.py, at the precision the document
used. Code, links and generated-table markers are skipped. Small integers (bus
numbers, counts up to 60) cannot be checked meaningfully this way and are accepted.
"""
import csv
import json
import re
import sys
from pathlib import Path

from . import config as C

NUM = re.compile(r"(?<![\w.])-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:e-?\d+)?")
# Tens of thousands of raw values match almost any number by rounding, so documents
# must quote the summary files instead.
RAW_DUMPS = {"hosting_breaches.csv"}
ALLOWED = {"1970", "2026", "3.12", "345", "15"}  # source year, memo date, Python version, nominal kV, run time


def _walk(x, out):
    if isinstance(x, dict):
        for v in x.values():
            _walk(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _walk(v, out)
    elif isinstance(x, bool):
        return
    elif isinstance(x, (int, float)):
        out.add(float(x))
    elif isinstance(x, str):
        for t in NUM.findall(x):  # numbers inside labels, such as "Line 23-24"
            out.add(float(t.replace(",", "")))


def sourced():
    vals = set()
    for f in sorted(C.RESULTS.iterdir()):
        if f.name in RAW_DUMPS:
            continue
        if f.suffix == ".json":
            _walk(json.loads(f.read_text()), vals)
        elif f.suffix == ".csv":
            with f.open() as fh:
                for row in csv.reader(fh):
                    for cell in row:
                        try:
                            vals.add(float(cell))
                        except ValueError:
                            _walk(cell, vals)
    for k, v in vars(C).items():
        if k.isupper() and not isinstance(v, Path):
            _walk(v, vals)
    return vals


def strip(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = re.sub(r"<!--.*?-->", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    return text


def matches(token, vals):
    t = token.replace(",", "")
    x = float(t)
    if token in ALLOWED or (float(x).is_integer() and 0 <= x <= 60):
        return True
    if "e" in t:
        return any(v != 0 and abs(v - x) <= 0.006 * abs(x) for v in vals)
    places = len(t.split(".")[1]) if "." in t else 0
    return any(round(v, places) == x or round(-v, places) == x for v in vals)


def check(paths):
    vals = sourced()
    bad = []
    for p in paths:
        for tok in NUM.findall(strip(Path(p).read_text())):
            if not matches(tok, vals):
                bad.append((Path(p).name, tok))
    return bad


def main():
    paths = sys.argv[1:] or [C.ROOT / "README.md", C.MEMO / "study_memo.md"]
    bad = check(paths)
    for name, tok in bad:
        print(f"UNSOURCED {name}: {tok}")
    print(f"check_numbers: {len(bad)} unsourced numbers in {len(paths)} files")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
