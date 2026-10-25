#!/usr/bin/env python3
"""Generate and update the lectures table in README.md.

Table section: ## 课件
Output columns:
  | 序号 | 课件 | 知识点 |

The 知识点 column is filled from ai/lectures/topics.json
(lecture folder name -> list of English keywords, max 5 each).
Lectures without an entry render as an em dash.

Incremental update behavior:
- Discover lecture folders (e.g. 0-overview, 1-prop-logic, ...).
- Include only folders containing both <name>.pdf and <name>-handout.pdf.
- Re-run the script after adding new lecture folders to refresh README.
- Add a topics.json entry for each new lecture to fill its 知识点 cell.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Update lectures table in README.md")
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
		"--topics",
		type=Path,
		default=None,
		help="Path to topics JSON (default: ai/lectures/topics.json)",
	)
	parser.add_argument(
		"--dry-run",
		action="store_true",
		help="Print generated table to stdout without writing README.md",
	)
	return parser.parse_args()


def discover_lectures_with_pdf(repo_root: Path) -> list[tuple[int, str]]:
	lectures: list[tuple[int, str]] = []
	pattern = re.compile(r"^(\d+)-")
	for child in repo_root.iterdir():
		if not child.is_dir():
			continue
		match = pattern.match(child.name)
		if not match:
			continue
		name = child.name
		if (child / f"{name}.pdf").exists() and (child / f"{name}-handout.pdf").exists():
			lectures.append((int(match.group(1)), name))

	lectures.sort(key=lambda item: item[0])
	return lectures


def load_topics(path: Path) -> dict[str, list[str]]:
	"""Load lecture -> keywords mapping; a missing file yields an empty mapping."""
	if not path.exists():
		return {}
	raw = json.loads(path.read_text(encoding="utf-8"))
	topics: dict[str, list[str]] = {}
	for lecture, keywords in raw.items():
		if lecture.startswith("_") or not isinstance(keywords, list):
			continue
		cleaned = [str(k).strip() for k in keywords if str(k).strip()]
		topics[lecture] = cleaned
	return topics


def build_table(lectures: list[tuple[int, str]], topics: dict[str, list[str]]) -> str:
	lines = [
		"| 序号 | 课件 | 知识点 |",
		"| :---: | :---: | :--- |",
	]
	for index, name in lectures:
		links = (
			f"[{name}](/{name}/{name}.pdf); "
			f"[{name}-handout](/{name}/{name}-handout.pdf)"
		)
		keywords = "; ".join(topics.get(name, [])) or "—"
		lines.append(f"| {index} | {links} | {keywords} |")
	return "\n".join(lines)


def replace_lectures_section(readme_text: str, table_text: str) -> str:
	marker = "## 课件"
	idx = readme_text.find(marker)
	if idx < 0:
		raise ValueError("README.md does not contain '## 课件' section")

	after = readme_text[idx:]
	if next_header := re.search(r"\n##\s+", after[1:]):
		section_end = idx + 1 + next_header.start()
		suffix = readme_text[section_end:]
	else:
		suffix = ""

	prefix = readme_text[:idx]
	new_section = f"## 课件\n\n{table_text}\n\n"
	return prefix + new_section + suffix.lstrip("\n")


def main() -> None:
	args = parse_args()
	repo_root = args.repo_root.resolve()
	readme = args.readme.resolve() if args.readme else repo_root / "README.md"
	topics_path = (
		args.topics.resolve()
		if args.topics
		else Path(__file__).resolve().parent / "topics.json"
	)

	if not readme.exists():
		raise FileNotFoundError(f"README.md not found: {readme}")

	lectures = discover_lectures_with_pdf(repo_root)
	topics = load_topics(topics_path)
	table_text = build_table(lectures, topics)

	if args.dry_run:
		print(table_text)
		return

	readme_text = readme.read_text(encoding="utf-8")
	new_text = replace_lectures_section(readme_text, table_text)
	readme.write_text(new_text, encoding="utf-8", newline="\n")
	print(f"Updated lectures table in {readme}")


if __name__ == "__main__":
	main()
