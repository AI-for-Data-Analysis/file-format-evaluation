from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "raw-logs"
DEFAULT_OUTPUT = ROOT / "sanitized-logs"

PATH_PREFIXES = [
    "/home/jessica-nash/analytics-accelerator/week-2-preparation",
    "/home/jessica-nash",
]

ID_KEYS = {
    "id",
    "parent_thread_id",
    "turn_id",
    "call_id",
}

UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s\"']+"),
    re.compile(r"(?i)\b(api[_-]?key|secret|password|token)\s*[:=]\s*[\"']?[^\"',\s]+"),
]


def stable_hash(value: str, prefix: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def sanitize_path_text(text: str) -> str:
    clean = text
    for path_prefix in PATH_PREFIXES:
        clean = clean.replace(path_prefix, "<workspace>")
    clean = re.sub(r"/home/[^/\s]+", "<home>", clean)
    clean = re.sub(r"/Users/[^/\s]+", "<home>", clean)
    return clean


def sanitize_secret_text(text: str) -> str:
    clean = text
    for pattern in SECRET_PATTERNS:
        if "authorization" in pattern.pattern.lower():
            clean = pattern.sub(r"\1[REDACTED_SECRET]", clean)
        elif "api" in pattern.pattern.lower() or "secret" in pattern.pattern.lower():
            clean = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED_SECRET]", clean)
        else:
            clean = pattern.sub("[REDACTED_SECRET]", clean)
    return clean


def sanitize_embedded_ids(text: str) -> str:
    return UUID_RE.sub(lambda match: stable_hash(match.group(0).lower(), "id"), text)


def sanitize_text(text: str) -> str:
    return sanitize_embedded_ids(sanitize_secret_text(sanitize_path_text(text)))


def sanitize_key(key: Any) -> Any:
    if isinstance(key, str):
        return sanitize_text(key)
    return key


def sanitize_value(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {sanitize_key(item_key): sanitize_value(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item, key) for item in value]
    if isinstance(value, str):
        if key in ID_KEYS:
            return stable_hash(value, key)
        return sanitize_text(value)
    return value


def output_name(path: Path, input_dir: Path) -> Path:
    relative = path.relative_to(input_dir)
    replacements = {
        "notebook-carson-019ec69e-fa32-7283-b6c6-fc26f2e1d8d8.jsonl": "notebook-carson.jsonl",
        "percent-cell-confucius-019ec69f-3714-7170-8901-7d4a0f4d47bb.jsonl": "percent-cell-confucius.jsonl",
        "boyle-notebook-019ec667-6341-7e52-a2c3-0b1cccf9e8fa.jsonl": "boyle-notebook.jsonl",
        "laplace-percent-cell-019ec667-910d-7222-b5c0-b0d2698617a3.jsonl": "laplace-percent-cell.jsonl",
    }
    return relative.with_name(replacements.get(relative.name, relative.name))


def sanitize_file(source: Path, destination: Path) -> tuple[int, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    records = 0
    bytes_written = 0
    with source.open(encoding="utf-8") as src, destination.open("w", encoding="utf-8") as dst:
        for line in src:
            if not line.strip():
                continue
            record = sanitize_value(json.loads(line))
            encoded = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
            dst.write(encoded + "\n")
            records += 1
            bytes_written += len(encoded) + 1
    return records, bytes_written


def scan_for_risks(path: Path) -> list[str]:
    findings = []
    text = path.read_text(encoding="utf-8")
    checks = {
        "absolute home path": r"/home/[^/\s]+|/Users/[^/\s]+",
        "uuid-like id": UUID_RE.pattern,
        "openai api key": r"\bsk-[A-Za-z0-9_-]{16,}\b",
        "github token": r"\bghp_[A-Za-z0-9_]{20,}\b",
        "authorization bearer token": r"(?i)authorization:\s*bearer\s+[^\s\"']+",
        "secret assignment": r"(?i)\b(api[_-]?key|secret|password|token)\s*[:=]\s*[\"']?[^\"',\s]+",
    }
    for label, pattern in checks.items():
        if re.search(pattern, text):
            findings.append(label)
    return findings


def remove_stale_generated_files(output_dir: Path, keep: set[Path]) -> None:
    for path in output_dir.rglob("*.jsonl"):
        if path not in keep:
            path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sanitize Codex JSONL session logs for publication.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Scan existing sanitized logs instead of regenerating them.")
    args = parser.parse_args()

    if args.check:
        paths = sorted(args.output_dir.rglob("*.jsonl"))
        if not paths:
            raise SystemExit(f"No sanitized logs found in {args.output_dir}")
        failed = False
        for path in paths:
            findings = scan_for_risks(path)
            if findings:
                failed = True
                print(f"FAIL {path.relative_to(ROOT)}: {', '.join(findings)}")
            else:
                print(f"OK   {path.relative_to(ROOT)}")
        raise SystemExit(1 if failed else 0)

    sources = sorted(args.input_dir.rglob("*.jsonl"))
    if not sources:
        raise SystemExit(f"No JSONL logs found in {args.input_dir}")

    destinations = {args.output_dir / output_name(source, args.input_dir) for source in sources}
    remove_stale_generated_files(args.output_dir, destinations)

    for source in sources:
        destination = args.output_dir / output_name(source, args.input_dir)
        records, bytes_written = sanitize_file(source, destination)
        print(f"Wrote {destination.relative_to(ROOT)} ({records} records, {bytes_written:,} bytes)")


if __name__ == "__main__":
    main()
