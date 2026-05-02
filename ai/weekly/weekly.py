#!/usr/bin/env python3
"""Generate and incrementally update the weekly schedule table in README.md.

Rules:
- Discover lecture folders like "0-overview", "1-prop-logic", ...
- Require both "<name>.pdf" and "<name>-handout.pdf"
- Preserve existing row fields (week/date/recording) for already listed lectures
- Auto-fill missing lecture rows with computed week/date and a default recording link
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path


DEFAULT_RECORDING_URL = ""
DEFAULT_START_DATE = "2026-03-03"


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
		"--recording-url",
		default=DEFAULT_RECORDING_URL,
		help="Fallback recording URL for newly added rows when no single-episode map is available",
	)
	parser.add_argument(
		"--recordings-map",
		type=Path,
		default=None,
		help="Path to JSON file mapping lecture -> list of BV IDs (default: ai/weekly/recordings_by_lecture.json)",
	)
	parser.add_argument(
		"--start-date",
		default=DEFAULT_START_DATE,
		help="Start date for the first session in YYYY-MM-DD",
	)
	parser.add_argument(
		"--dry-run",
		action="store_true",
		help="Print generated table to stdout without writing README.md",
	)
	return parser.parse_args()


def discover_lectures(repo_root: Path) -> list[str]:
	lectures: list[tuple[int, str]] = []
	pattern = re.compile(r"^(\d+)-")
	for child in repo_root.iterdir():
		if not child.is_dir():
			continue
		m = pattern.match(child.name)
		if not m:
			continue

		base = child.name
		pdf = child / f"{base}.pdf"
		handout = child / f"{base}-handout.pdf"
		if pdf.exists() and handout.exists():
			lectures.append((int(m.group(1)), base))

	lectures.sort(key=lambda x: x[0])
	return [name for _, name in lectures]


def compute_dates(start_date: dt.date, count: int) -> list[dt.date]:
	# Two sessions per week: Tue (+3 days) then Fri (+4 days) repeating.
	increments = [3, 4]
	dates = [start_date]
	for i in range(1, count):
		dates.append(dates[-1] + dt.timedelta(days=increments[(i - 1) % 2]))
	return dates


def parse_existing_rows(readme_text: str) -> dict[str, dict[str, str]]:
	"""Return mapping: lecture name -> {week, date, recording} from current table."""
	existing: dict[str, dict[str, str]] = {}
	row_re = re.compile(
		r"^\|\s*(?P<week>[^|]+?)\s*\|\s*(?P<date>[^|]+?)\s*\|\s*(?P<slides>[^|]+?)\s*\|\s*(?P<recording>[^|]*?)\s*\|\s*$"
	)
	lecture_re = re.compile(r"\[([^\]]+)\]\(/\1/\1\.pdf\)")

	for line in readme_text.splitlines():
		m = row_re.match(line)
		if not m:
			continue
		slides = m.group("slides")
		lm = lecture_re.search(slides)
		if not lm:
			continue
		lecture = lm.group(1)
		existing[lecture] = {
			"week": m.group("week").strip(),
			"date": m.group("date").strip(),
			"recording": m.group("recording").strip(),
		}
	return existing


def load_recordings_map(recordings_map_path: Path) -> dict[str, list[str]]:
	if not recordings_map_path.exists():
		return {}
	data = json.loads(recordings_map_path.read_text(encoding="utf-8"))
	result: dict[str, list[str]] = {}
	for k, v in data.items():
		if isinstance(v, list):
			result[k] = [str(x).strip() for x in v if str(x).strip()]
	return result


def format_recording_links(lecture: str, bvids: list[str]) -> str:
	links = []
	for i, bvid in enumerate(bvids, start=1):
		links.append(f"[{lecture}-({i})](https://www.bilibili.com/video/{bvid}/)")
	return "; ".join(links)


def build_table(
	lectures: list[str],
	existing: dict[str, dict[str, str]],
	start_date: dt.date,
	recording_url: str,
	recordings_map: dict[str, list[str]],
) -> str:
	dates = compute_dates(start_date, len(lectures))
	lines = [
		"| 周次 | 日期 | 课件 | 课堂录屏 |",
		"| :---: | :---: | :---: | :---: |",
	]

	default_recording = f"[课堂录屏合集]({recording_url})" if recording_url else ""

	for i, lec in enumerate(lectures):
		week = str((i // 2) + 1)
		date = dates[i].isoformat()
		slides = f"[{lec}](/{lec}/{lec}.pdf); [{lec}-handout](/{lec}/{lec}-handout.pdf)"
		recording = format_recording_links(lec, recordings_map.get(lec, [])) or default_recording

		if lec in existing:
			week = existing[lec]["week"] or week
			date = existing[lec]["date"] or date
			if existing[lec]["recording"]:
				recording = existing[lec]["recording"]

		lines.append(f"| {week} | {date} | {slides} | {recording} |")

	return "\n".join(lines)


def replace_weekly_section(readme_text: str, table_text: str) -> str:
	marker = "## 周历"
	idx = readme_text.find(marker)
	if idx < 0:
		raise ValueError("README.md does not contain '## 周历' section")

	after = readme_text[idx:]
	next_header = re.search(r"\n##\s+", after[1:])
	if next_header:
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

	start_date = dt.date.fromisoformat(args.start_date)
	lectures = discover_lectures(repo_root)
	if not lectures:
		raise RuntimeError("No lecture folders with both pdf/handout found")

	recordings_map_path = (
		args.recordings_map.resolve()
		if args.recordings_map
		else repo_root / "ai" / "weekly" / "recordings_by_lecture.json"
	)
	recordings_map = load_recordings_map(recordings_map_path)

	readme_text = readme.read_text(encoding="utf-8")
	existing = parse_existing_rows(readme_text)
	table_text = build_table(lectures, existing, start_date, args.recording_url, recordings_map)
	new_text = replace_weekly_section(readme_text, table_text)

	if args.dry_run:
		print(table_text)
		return

	readme.write_text(new_text, encoding="utf-8", newline="\n")
	print(f"Updated weekly schedule in {readme}")


if __name__ == "__main__":
	main()
