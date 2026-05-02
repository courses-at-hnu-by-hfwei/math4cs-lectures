#!/usr/bin/env python3
"""Generate and update the weekly schedule table in README.md.

Table structure: one row per actual class-session date.
Data source: ai/weekly/recordings_by_lecture.json
  {lecture: [{bvid, date}, ...], ...}
  where "date" is the actual class date extracted from the video title
  (format YYYYMMDD prefix in title), NOT the upload/publish date.

Week numbering: starts from the Monday specified by --week-start
(default 2026-03-02), so that date's week == 1.

Incremental update: add new recordings to recordings_by_lecture.json;
re-run the script to regenerate the table.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections import defaultdict
from pathlib import Path


DEFAULT_WEEK1_MONDAY = "2026-03-02"


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Update weekly table in README.md")
	parser.add_argument(
		"--repo-root",
		type=Path,
		default=Path(__file__).resolve().parents[2],
		help="Path to math4cs-lectures repository root",
	)
	parser.add_argument(
		"--readme",
		type=Path,
		default=None,
		help="Path to README.md (default: <repo-root>/README.md)",
	)
	parser.add_argument(
		"--recordings-map",
		type=Path,
		default=None,
		help="Path to JSON file (default: ai/weekly/recordings_by_lecture.json)",
	)
	parser.add_argument(
		"--week-start",
		default=DEFAULT_WEEK1_MONDAY,
		help="Monday of week 1 in YYYY-MM-DD (default: 2026-03-02)",
	)
	parser.add_argument(
		"--dry-run",
		action="store_true",
		help="Print generated table to stdout without writing README.md",
	)
	return parser.parse_args()


def load_recordings_map(path: Path) -> dict[str, list[dict]]:
	"""Load recordings_by_lecture.json.

	Supports both legacy format (list of BV strings) and new format
	(list of {bvid, date} objects).  Entries without a date are skipped
	in the date-based table but preserved in the file unchanged.
	"""
	if not path.exists():
		return {}
	raw = json.loads(path.read_text(encoding="utf-8"))
	result: dict[str, list[dict]] = {}
	for lecture, entries in raw.items():
		if lecture.startswith("_"):   # skip comment keys
			continue
		if not isinstance(entries, list):
			continue
		normalised = []
		for e in entries:
			if isinstance(e, str):
				normalised.append({"bvid": e.strip(), "date": None})
			elif isinstance(e, dict):
				normalised.append({"bvid": str(e.get("bvid", "")).strip(),
									"date": e.get("date")})
		result[lecture] = normalised
	return result


def week_number(date: dt.date, week1_monday: dt.date) -> int:
	return (date - week1_monday).days // 7 + 1


def build_table(
	recordings_map: dict[str, list[dict]],
	week1_monday: dt.date,
) -> str:
	# Build per-date list of (lecture, bvid, per-lecture-index)
	# per-lecture-index: sequential index within that lecture's recording list
	date_rows: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
	for lecture, recs in recordings_map.items():
		for idx, rec in enumerate(recs, start=1):
			bvid = rec.get("bvid", "")
			date_str = rec.get("date")
			if bvid and date_str:
				date_rows[date_str].append((lecture, bvid, idx))

	lines = [
		"| 周次 | 日期 | 课堂录屏 |",
		"| :---: | :---: | :---: |",
	]

	for date_str in sorted(date_rows):
		date = dt.date.fromisoformat(date_str)
		week = week_number(date, week1_monday)
		entries = date_rows[date_str]

		# Recordings cell
		rec_parts = [
			f"[{lecture}-({idx})](https://www.bilibili.com/video/{bvid}/)"
			for lecture, bvid, idx in entries
		]
		recordings = "; ".join(rec_parts)

		lines.append(f"| {week} | {date_str} | {recordings} |")

	return "\n".join(lines)


def replace_weekly_section(readme_text: str, table_text: str) -> str:
	marker = "## 周历"
	idx = readme_text.find(marker)
	if idx < 0:
		raise ValueError("README.md does not contain '## 周历' section")

	after = readme_text[idx:]
	if next_header := re.search(r"\n##\s+", after[1:]):
		section_end = idx + 1 + next_header.start()
		suffix = readme_text[section_end:]
	else:
		suffix = ""

	prefix = readme_text[:idx]
	new_section = f"## 周历\n\n{table_text}\n\n"
	return prefix + new_section + suffix.lstrip("\n")


def main() -> None:
	args = parse_args()
	repo_root = args.repo_root.resolve()
	readme = args.readme.resolve() if args.readme else repo_root / "README.md"

	if not readme.exists():
		raise FileNotFoundError(f"README.md not found: {readme}")

	week1_monday = dt.date.fromisoformat(args.week_start)

	recordings_map_path = (
		args.recordings_map.resolve()
		if args.recordings_map
		else repo_root / "ai" / "weekly" / "recordings_by_lecture.json"
	)
	recordings_map = load_recordings_map(recordings_map_path)

	table_text = build_table(recordings_map, week1_monday)

	if args.dry_run:
		print(table_text)
		return

	readme_text = readme.read_text(encoding="utf-8")
	new_text = replace_weekly_section(readme_text, table_text)
	readme.write_text(new_text, encoding="utf-8", newline="\n")
	print(f"Updated weekly schedule in {readme}")


if __name__ == "__main__":
	main()
