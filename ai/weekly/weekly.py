#!/usr/bin/env python3
"""Incrementally sync recordings map and regenerate the weekly table.

This script can do two things in one run:
1) Sync ai/weekly/recordings_by_lecture.json from Bilibili playlist archives.
2) Regenerate README.md section "## 周历" as a date-based table.

The recordings map format is:
{
  "_comment": "...",
  "_week_start": "2026-03-02",
  "1-prop-logic": [{"bvid": "BV...", "date": "YYYY-MM-DD"}, ...],
  ...
}
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path


DEFAULT_WEEK1_MONDAY = "2026-03-02"
DEFAULT_PLAYLIST_MID = 479141149
DEFAULT_PLAYLIST_SEASON_ID = 7582381


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Sync recordings map and update weekly table")
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
		help="Path to recordings JSON (default: ai/weekly/recordings_by_lecture.json)",
	)
	parser.add_argument(
		"--week-start",
		default=DEFAULT_WEEK1_MONDAY,
		help="Monday of week 1 in YYYY-MM-DD (default: 2026-03-02)",
	)
	parser.add_argument(
		"--dry-run",
		action="store_true",
		help="Print generated weekly table without writing files",
	)
	parser.add_argument(
		"--no-sync-recordings",
		action="store_true",
		help="Skip updating recordings_by_lecture.json from archives",
	)
	parser.add_argument(
		"--archives-json",
		type=Path,
		default=None,
		help="Optional local JSON file containing playlist archives array",
	)
	parser.add_argument(
		"--playlist-mid",
		type=int,
		default=DEFAULT_PLAYLIST_MID,
		help="Bilibili uploader mid (default: 479141149)",
	)
	parser.add_argument(
		"--season-id",
		type=int,
		default=DEFAULT_PLAYLIST_SEASON_ID,
		help="Bilibili playlist season_id (default: 7582381)",
	)
	parser.add_argument(
		"--cookie",
		default="",
		help="Optional Cookie header for Bilibili API requests",
	)
	parser.add_argument(
		"--strict-sync",
		action="store_true",
		help="Fail immediately if remote sync fails",
	)
	return parser.parse_args()


def discover_lecture_folders(repo_root: Path) -> dict[int, str]:
	"""Map lecture number to canonical folder name, e.g. 1 -> 1-prop-logic."""
	result: dict[int, str] = {}
	pattern = re.compile(r"^(\d+)-")
	for child in repo_root.iterdir():
		if not child.is_dir():
			continue
		if match := pattern.match(child.name):
			result[int(match.group(1))] = child.name
	return result


def load_recordings_map(path: Path) -> dict[str, list[dict[str, str]]]:
	"""Load recordings map and normalize entries to {bvid, date} objects."""
	if not path.exists():
		return {}
	raw = json.loads(path.read_text(encoding="utf-8"))
	result: dict[str, list[dict[str, str]]] = {}
	for lecture, entries in raw.items():
		if lecture.startswith("_") or not isinstance(entries, list):
			continue
		normalized: list[dict[str, str]] = []
		for entry in entries:
			if isinstance(entry, str):
				if bvid := entry.strip():
					normalized.append({"bvid": bvid, "date": ""})
			elif isinstance(entry, dict):
				if bvid := str(entry.get("bvid", "")).strip():
					normalized.append({"bvid": bvid, "date": str(entry.get("date", "")).strip()})
		result[lecture] = normalized
	return result


def write_recordings_map(path: Path, data: dict[str, list[dict[str, str]]], week_start: str) -> None:
	"""Write map with stable ordering and metadata keys."""
	ordered: dict[str, object] = {
		"_comment": "date: actual class date extracted from video title (YYYYMMDD prefix in title), NOT upload date.",
		"_week_start": week_start,
	}
	for lecture in sorted(data.keys(), key=lecture_sort_key):
		ordered[lecture] = data[lecture]
	path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def lecture_sort_key(name: str) -> tuple[int, str]:
	return (int(match.group(1)), name) if (match := re.match(r"^(\d+)-", name)) else (10**9, name)


def fetch_archives_from_api(mid: int, season_id: int, cookie: str = "") -> list[dict]:
	"""Fetch all archives from Bilibili playlist API with pagination."""
	archives: list[dict] = []
	page_num = 1
	page_size = 100
	while True:
		params = urllib.parse.urlencode(
			{"mid": mid, "season_id": season_id, "page_num": page_num, "page_size": page_size}
		)
		url = f"https://api.bilibili.com/x/polymer/web-space/seasons_archives_list?{params}"
		headers = {
			"User-Agent": "Mozilla/5.0",
			"Accept": "application/json",
		}
		if cookie:
			headers["Cookie"] = cookie
		request = urllib.request.Request(url=url, headers=headers, method="GET")
		with urllib.request.urlopen(request, timeout=20) as response:
			payload = json.loads(response.read().decode("utf-8"))

		if payload.get("code") != 0:
			raise RuntimeError(f"Bilibili API returned code={payload.get('code')} message={payload.get('message')}")

		page_archives = payload.get("data", {}).get("archives", [])
		if not page_archives:
			break
		archives.extend(page_archives)
		if len(page_archives) < page_size:
			break
		page_num += 1
	return archives


def load_archives_from_file(path: Path) -> list[dict]:
	"""Load archives list from local json file."""
	payload = json.loads(path.read_text(encoding="utf-8"))
	if isinstance(payload, list):
		return payload
	if isinstance(payload, dict):
		if isinstance(payload.get("archives"), list):
			return payload["archives"]
		if isinstance(payload.get("data", {}).get("archives"), list):
			return payload["data"]["archives"]
	raise ValueError("archives json must contain a list or {archives: [...]}/{data:{archives:[...]}}")


def parse_recording_from_title(title: str, lecture_folders: dict[int, str]) -> tuple[str, str] | None:
	"""Parse title to (lecture, date). Expected title contains YYYYMMDD and lecture index."""
	date_match = re.search(r"\b(20\d{6})\b", title)
	lecture_match = re.search(r"(?:^|-)math4cs-(\d+)-", title, flags=re.IGNORECASE)
	if not date_match or not lecture_match:
		return None
	lecture_num = int(lecture_match.group(1))
	lecture = lecture_folders.get(lecture_num)
	if not lecture:
		return None
	raw_date = date_match.group(1)
	date_str = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
	return lecture, date_str


def merge_archives_into_recordings(
	existing: dict[str, list[dict[str, str]]],
	archives: list[dict],
	lecture_folders: dict[int, str],
) -> dict[str, list[dict[str, str]]]:
	"""Incrementally merge archives by bvid; append new entries and fill missing dates."""
	result: dict[str, list[dict[str, str]]] = {k: [dict(item) for item in v] for k, v in existing.items()}
	index: dict[str, tuple[str, int]] = {}
	for lecture, entries in result.items():
		for i, item in enumerate(entries):
			if bvid := item.get("bvid", ""):
				index[bvid] = (lecture, i)

	for archive in archives:
		bvid = str(archive.get("bvid", "")).strip()
		title = str(archive.get("title", ""))
		if not bvid:
			continue
		parsed = parse_recording_from_title(title, lecture_folders)
		if not parsed:
			continue
		lecture, date_str = parsed

		if bvid in index:
			old_lecture, idx = index[bvid]
			if not result[old_lecture][idx].get("date") and date_str:
				result[old_lecture][idx]["date"] = date_str
			continue

		result.setdefault(lecture, []).append({"bvid": bvid, "date": date_str})
		index[bvid] = (lecture, len(result[lecture]) - 1)

	return result


def week_number(date: dt.date, week1_monday: dt.date) -> int:
	return (date - week1_monday).days // 7 + 1


def build_table(recordings_map: dict[str, list[dict[str, str]]], week1_monday: dt.date) -> str:
	date_rows: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
	for lecture, recs in recordings_map.items():
		for idx, rec in enumerate(recs, start=1):
			bvid = rec.get("bvid", "")
			date_str = rec.get("date", "")
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
		recordings = "; ".join(
			f"[{lecture}-({idx})](https://www.bilibili.com/video/{bvid}/)"
			for lecture, bvid, idx in entries
		)
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
	recordings_map_path = (
		args.recordings_map.resolve()
		if args.recordings_map
		else repo_root / "ai" / "weekly" / "recordings_by_lecture.json"
	)

	if not readme.exists():
		raise FileNotFoundError(f"README.md not found: {readme}")

	week1_monday = dt.date.fromisoformat(args.week_start)
	recordings_map = load_recordings_map(recordings_map_path)

	if not args.no_sync_recordings:
		try:
			lecture_folders = discover_lecture_folders(repo_root)
			if args.archives_json:
				archives = load_archives_from_file(args.archives_json.resolve())
			else:
				archives = fetch_archives_from_api(args.playlist_mid, args.season_id, args.cookie)
			recordings_map = merge_archives_into_recordings(recordings_map, archives, lecture_folders)
			if not args.dry_run:
				write_recordings_map(recordings_map_path, recordings_map, args.week_start)
		except Exception as exc:
			if args.strict_sync:
				raise
			print(f"Warning: recordings sync skipped due to error: {exc}")

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
