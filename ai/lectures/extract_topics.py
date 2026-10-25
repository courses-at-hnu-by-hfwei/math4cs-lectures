#!/usr/bin/env python3
r"""LLM-centric knowledge-point extraction pipeline for the 课件 table.

Design principle
----------------
Deterministic rules alone produce noisy keyword lists, and an LLM alone is
not reproducible. This pipeline therefore splits the work into three stages
with different trust models:

  [1] harvest  (deterministic, high recall)
      Scan lecture .tex sources for *raw signals* only:
        - emphasis macros from preamble.tex (\bfit, \red/\green/\blue/...,
          \rbox/\gbox/\bbox/\pbox, overlays)
        - theorem/definition/lemma/corollary/proposition/axiom titles
        - frame titles and active part (chapter) names
      Signals are normalized and counted; nothing is judged here.

  [2] curate   (LLM semantic selection -- the core of the pipeline)
      An LLM receives, per lecture: the title, the active chapter structure,
      and the top candidate signals with counts. It selects <=5 English
      keywords following explicit quality criteria (core-ness, specificity,
      form, merging, coverage, count, provenance).
      Two invocation modes:
        --llm api : call an OpenAI-compatible chat API (credentials via env)
        packet    : `pack` renders a self-contained prompt packet
                   (topics_prompt.md); any LLM or human fills the response
                   JSON (topics_response.json) following the same schema.

  [3] merge    (deterministic guardrails)
      Validate the LLM response against hard rules (count 1..5, English
      only, word/char limits, stopwords, in-lecture dedup, and provenance:
      every keyword must cite a real harvested signal), then merge into
      topics.json incrementally (lectures absent from the response keep
      their current entry).

Usage (from the repository root):
    python ai/lectures/extract_topics.py harvest
    python ai/lectures/extract_topics.py pack
    python ai/lectures/extract_topics.py curate --llm api   # or: fill packet by hand
    python ai/lectures/extract_topics.py merge [--strict]

Intermediates (topics_candidates.json, topics_prompt.md,
topics_response.json) are gitignored; topics.json is the committed output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CANDIDATES = SCRIPT_DIR / "topics_candidates.json"
DEFAULT_PROMPT = SCRIPT_DIR / "topics_prompt.md"
DEFAULT_RESPONSE = SCRIPT_DIR / "topics_response.json"
DEFAULT_TOPICS = SCRIPT_DIR / "topics.json"

# --------------------------------------------------------------------------
# Signal harvesting configuration (mirrors preamble.tex)
# --------------------------------------------------------------------------

MACRO_EMPHASIS = ["bfit"]
MACRO_COLOR = [
	"red", "green", "blue", "purple", "teal", "orange",
	"cyan", "brown", "violet", "yellow",
]
MACRO_BOX = ["rbox", "gbox", "bbox", "pbox"]
MACRO_OVERLAY = ["redoverlay", "blueoverlay"]
ALL_MACROS = MACRO_EMPHASIS + MACRO_COLOR + MACRO_BOX + MACRO_OVERLAY

THEOREM_ENVS = [
	"theorem", "definition", "lemma", "corollary", "proposition", "axiom",
]

# Keywords rejected regardless of provenance (generic filler).
KEYWORD_STOPLIST = {
	"introduction", "intro", "overview", "suggestion", "conclusion",
	"summary", "history", "todo", "example", "examples", "problem",
	"problems", "question", "questions", "note", "notes", "remark",
	"math", "mathematics", "method", "methods", "property", "properties",
	"definition", "theorem", "lemma", "proof", "idea", "application",
}

# A keyword whose every word is a function word / filler verb is rejected.
KEYWORD_FRAGMENTS = {
	"the", "a", "an", "and", "or", "not", "no", "iff", "if", "is", "are",
	"was", "were", "be", "been", "of", "to", "in", "on", "at", "by", "for",
	"with", "from", "that", "this", "it", "as", "we", "all", "any", "both",
	"either", "neither", "nor", "every", "each", "there", "then", "so",
	"can", "will", "let", "suppose", "take", "construct", "check", "given",
}

MAX_KEYWORDS = 5
MAX_KEYWORD_WORDS = 6
MAX_KEYWORD_CHARS = 60
MIN_SIGNAL_MATCH_LEN = 4

# --------------------------------------------------------------------------
# LLM prompt: quality criteria (shared by packet mode and API mode)
# --------------------------------------------------------------------------

CRITERIA = """你是《计算机中的数学》(math4cs) 课程的知识点提炼专家。给定一讲讲义的结构信息与候选信号池，为该讲挑选最多 5 个英文关键词，概括其核心知识点。

# 筛选与质量标准（按优先级，必须全部满足）
1. 核心性：只选主线知识点——在讲义中被着重强调（粗斜体、颜色高亮、彩色框）、独立成定理/定义、或贯穿多个章节的概念。顺带提及、例子、花絮、过渡页一律不选。
2. 特异性：优先具体的概念名、定理名、算法名、结构名（如 "Hall's Theorem"、"Hasse Diagrams"）；避免泛词（如 math、graph、problem、method、property、note）。
3. 形态规范：英文；1-6 个词；总长不超过 60 字符；使用概念名或定理名（可用 Title Case）；禁止公式、变元名（p/q/x/y）、碎片（not/iff/the/and）、文件名、URL、任何中文。
4. 合并去重：同义、近义或上下位信号合并为一个关键词（如 "M-alternating Paths" 与 "M-augmenting Paths" 合并为 "M-Augmenting Paths"）；同一讲内不得出现近义重复。
5. 覆盖性：所选关键词合起来须覆盖该讲主要章节（对照 parts 列表），不遗漏主线；也不为凑数添加边缘内容。
6. 数量：每讲 1-5 个；核心内容不足 5 个时取 3-4 个即可，严禁凑数。
7. 可溯源：每个关键词必须在 from 字段引用候选池中真实出现的信号原文（允许翻译与概括，但必须有据）。

# 输出格式（严格 JSON，不要输出任何其他文字）
{"lecture": "<讲次目录名>", "keywords": [{"en": "<英文关键词>", "from": ["<候选池中的信号原文>", ...]}, ...]}"""

RESPONSE_SCHEMA_EXAMPLE = """{
  "lectures": [
    {
      "lecture": "2-predicate-logic",
      "keywords": [
        {"en": "Quantifiers", "from": ["forall", "exists"]},
        {"en": "Free & Bound Variables", "from": ["自由 (free) 变元", "约束 (bound) 变元"]}
      ]
    }
  ]
}"""


# --------------------------------------------------------------------------
# Low-level LaTeX helpers
# --------------------------------------------------------------------------

def extract_braced(text: str, start: int) -> tuple[str, int]:
	"""start = index of the opening '{'; return (inner, index after closing)."""
	depth = 0
	for i in range(start, len(text)):
		if text[i] == "{":
			depth += 1
		elif text[i] == "}":
			depth -= 1
			if depth == 0:
				return text[start + 1 : i], i
	return text[start + 1 :], len(text) - 1


def macro_usages(text: str, macro: str) -> list[str]:
	out = []
	for m in re.finditer(r"\\" + macro + r"(?![a-zA-Z])\{", text):
		inner, _ = extract_braced(text, m.end() - 1)
		out.append(inner)
	return out


def clean_span(span: str) -> str:
	"""Display-oriented cleanup of a raw LaTeX span."""
	s = span.strip()
	s = re.sub(r"\$+", "", s)
	s = re.sub(r"\\[a-zA-Z]+\*?", " ", s)
	s = re.sub(r"[{}\\]", " ", s)
	s = re.sub(r"\s+", " ", s).strip(" .,;:，。；：、")
	return s


def normalize(s: str) -> str:
	"""Aggressive normalization for dedup and provenance matching."""
	s = s.lower()
	s = re.sub(r"\$+", " ", s)
	s = re.sub(r"\\[a-zA-Z]+\*?", " ", s)
	s = re.sub(r"[{}\\]", " ", s)
	s = re.sub(r"[^\w\s\-'–—]", " ", s)
	s = re.sub(r"\s+", " ", s).strip()
	return s


def has_ascii_letter(s: str) -> bool:
	return re.search(r"[A-Za-z]", s) is not None


def has_cjk(s: str) -> bool:
	return re.search(r"[\u4e00-\u9fff]", s) is not None


def strip_comments(text: str) -> str:
	return re.sub(r"(?<!\\)%.*", "", text)


# --------------------------------------------------------------------------
# Lecture discovery (same filter as lectures.py)
# --------------------------------------------------------------------------

def discover_lectures(repo_root: Path) -> list[str]:
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
	return [name for _, name in lectures]


def lecture_title(main_tex: str) -> str:
	m = re.search(r"\\title(?:\[[^\]]*\])?\{", main_tex)
	if not m:
		return ""
	inner, _ = extract_braced(main_tex, m.end() - 1)
	return clean_span(inner)


# --------------------------------------------------------------------------
# Stage 1: harvest
# --------------------------------------------------------------------------

def resolve_active_files(lecture_dir: Path, main_tex_path: Path) -> list[Path]:
	"""Transitive closure of \\input starting from the main tex.

	Parts may themselves \\input other parts (e.g. relation.tex inputs
	relation-operation); only files reachable from the master file are part
	of the delivered lecture. Resolution stays inside the lecture directory
	(LaTeX resolves \\input relative to the master file's directory).
	"""
	files: list[Path] = []
	seen: set[Path] = set()
	queue: list[Path] = [main_tex_path]
	while queue:
		p = queue.pop(0)
		rp = p.resolve()
		if rp in seen:
			continue
		seen.add(rp)
		if not p.exists():
			continue
		files.append(p)
		try:
			text = p.read_text(encoding="utf-8", errors="replace")
		except OSError:
			continue
		for line in strip_comments(text).splitlines():
			for m in re.finditer(r"\\input\{([^}]+)\}", line):
				target = m.group(1).strip()
				for base in (lecture_dir, p.parent):
					cand = base / target
					if cand.suffix != ".tex":
						cand = cand.with_suffix(".tex")
					try:
						inside = cand.resolve().is_relative_to(lecture_dir.resolve())
					except ValueError:
						inside = False
					if inside and cand.exists():
						queue.append(cand)
						break
	return files


def active_part_names(lecture_dir: Path, files: list[Path]) -> list[str]:
	"""Names of active part files (parts/*.tex), in input order."""
	names: list[str] = []
	for f in files:
		try:
			rel = f.resolve().relative_to(lecture_dir.resolve())
		except ValueError:
			continue
		if len(rel.parts) == 2 and rel.parts[0] == "parts":
			names.append(rel.parts[1][: -len(".tex")])
	return names


def harvest_lecture(name: str, lecture_dir: Path) -> dict:
	pool: dict[str, dict] = {}

	def add(text: str, source: str) -> None:
		cleaned = clean_span(text)
		if not cleaned or len(cleaned) > 80:
			return
		norm = normalize(cleaned)
		if len(norm) < 2:
			return
		if not has_ascii_letter(norm) and not has_cjk(norm):
			return  # pure math/symbol fragment
		entry = pool.setdefault(
			norm, {"text": cleaned, "norm": norm, "count": 0, "sources": []}
		)
		entry["count"] += 1
		if source not in entry["sources"]:
			entry["sources"].append(source)

	main_tex_path = lecture_dir / f"{name}.tex"
	main_tex = (
		main_tex_path.read_text(encoding="utf-8", errors="replace")
		if main_tex_path.exists()
		else ""
	)
	files = (
		resolve_active_files(lecture_dir, main_tex_path)
		if main_tex_path.exists()
		else []
	)
	if not files:  # fallback: no master tex, scan top-level tex files
		files = sorted(lecture_dir.glob("*.tex"))
	parts = active_part_names(lecture_dir, files)

	for f in files:
		text = f.read_text(encoding="utf-8", errors="replace")
		for macro in ALL_MACROS:
			for span in macro_usages(text, macro):
				add(span, "emph")
		for env in THEOREM_ENVS:
			for m in re.finditer(r"\\begin\{" + env + r"\}(?:\[([^\]]*)\])?", text):
				title = m.group(1)
				if title:
					add(title, "theorem")
		for m in re.finditer(r"\\frametitle\{", text):
			inner, _ = extract_braced(text, m.end() - 1)
			add(inner, "frame")
		for m in re.finditer(r"\\begin\{frame\}(?:\[[^\]]*\])?\{", text):
			inner, _ = extract_braced(text, m.end() - 1)
			add(inner, "frame")

	for part in parts:
		add(part.replace("-", " "), "part")

	candidates = sorted(pool.values(), key=lambda e: (-e["count"], e["norm"]))
	return {
		"lecture": name,
		"title": lecture_title(main_tex),
		"parts": parts,
		"candidates": candidates,
	}


def cmd_harvest(args: argparse.Namespace) -> None:
	lectures = discover_lectures(REPO_ROOT)
	data = {"lectures": [harvest_lecture(name, REPO_ROOT / name) for name in lectures]}
	args.candidates.write_text(
		json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
	)
	total = sum(len(l["candidates"]) for l in data["lectures"])
	print(f"harvested {len(lectures)} lectures, {total} candidate signals -> {args.candidates}")


# --------------------------------------------------------------------------
# Stage 2: curate (LLM)
# --------------------------------------------------------------------------

def render_lecture_context(entry: dict, top_n: int, top_structural: int) -> str:
	lines = [
		f"讲次: {entry['lecture']}",
		f"标题: {entry['title'] or '(无)'}",
		f"章节 (parts): {'; '.join(entry['parts']) if entry['parts'] else '(无)'}",
		"候选信号池 (次数 | 来源 | 信号文本):",
	]
	source_label = {"emph": "强调", "theorem": "定理标题", "frame": "帧标题", "part": "章节名"}
	structural = [c for c in entry["candidates"] if set(c["sources"]) - {"emph"}]
	emph_only = [c for c in entry["candidates"] if not (set(c["sources"]) - {"emph"})]
	for cand in structural[:top_structural] + emph_only[:top_n]:
		sources = "/".join(source_label.get(s, s) for s in cand["sources"])
		lines.append(f"{cand['count']} | {sources} | {cand['text']}")
	return "\n".join(lines)


def cmd_pack(args: argparse.Namespace) -> None:
	data = json.loads(args.candidates.read_text(encoding="utf-8"))
	sections = [
		"# math4cs 知识点提取提示词包",
		"",
		"按下方「系统指令」与每讲的「候选信号池」，为每一讲挑选最多 5 个英文关键词，",
		f"并将结果保存为 `{args.response.name}`（JSON 格式见文末），然后运行：",
		"",
		"```bash",
		"python ai/lectures/extract_topics.py merge",
		"```",
		"",
		"## 系统指令（筛选与质量标准）",
		"",
		CRITERIA,
		"",
		"## 响应文件格式",
		"",
		"```json",
		RESPONSE_SCHEMA_EXAMPLE,
		"```",
	]
	for entry in data["lectures"]:
		sections += ["", "---", "", "```", render_lecture_context(entry, args.top, args.top_structural), "```"]
	args.prompt.write_text("\n".join(sections) + "\n", encoding="utf-8", newline="\n")
	print(f"prompt packet for {len(data['lectures'])} lectures -> {args.prompt}")
	print("next: run it through any LLM, save the JSON response, then `merge`")


def call_llm_api(system: str, user: str) -> str:
	base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
	key = os.environ.get("LLM_API_KEY", "")
	model = os.environ.get("LLM_MODEL", "")
	if not base or not key or not model:
		raise RuntimeError(
			"LLM API mode requires env vars LLM_BASE_URL, LLM_API_KEY, LLM_MODEL"
		)
	body = json.dumps(
		{
			"model": model,
			"temperature": 0,
			"messages": [
				{"role": "system", "content": system},
				{"role": "user", "content": user},
			],
			"response_format": {"type": "json_object"},
		}
	).encode("utf-8")
	request = urllib.request.Request(
		url=f"{base}/chat/completions",
		data=body,
		headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
		method="POST",
	)
	with urllib.request.urlopen(request, timeout=180) as response:
		payload = json.loads(response.read().decode("utf-8"))
	return payload["choices"][0]["message"]["content"]


def parse_llm_json(raw: str) -> dict:
	text = raw.strip()
	if text.startswith("```"):
		text = re.sub(r"^```(?:json)?\s*", "", text)
		text = re.sub(r"\s*```$", "", text)
	start, end = text.find("{"), text.rfind("}")
	if start < 0 or end <= start:
		raise ValueError("no JSON object found in LLM response")
	return json.loads(text[start : end + 1])


def cmd_curate(args: argparse.Namespace) -> None:
	if args.llm != "api":
		print("packet mode: run `pack` first, let an LLM fill the response, then `merge`.")
		print("for fully automated curation use: curate --llm api")
		print("(requires env vars LLM_BASE_URL, LLM_API_KEY, LLM_MODEL)")
		return

	data = json.loads(args.candidates.read_text(encoding="utf-8"))
	lectures_out = []
	for entry in data["lectures"]:
		user = render_lecture_context(entry, args.top, args.top_structural)
		parsed = None
		for attempt in range(1, args.retries + 2):
			try:
				raw = call_llm_api(CRITERIA, user)
				parsed = parse_llm_json(raw)
				if parsed.get("lecture") != entry["lecture"]:
					raise ValueError(f"unexpected lecture field: {parsed.get('lecture')!r}")
				break
			except Exception as exc:
				print(f"  [{entry['lecture']}] attempt {attempt} failed: {exc}")
				parsed = None
				time.sleep(2 * attempt)
		if parsed is None:
			raise RuntimeError(f"LLM curation failed for {entry['lecture']}")
		lectures_out.append(parsed)
		print(f"  [{entry['lecture']}] {len(parsed.get('keywords', []))} keywords")
	args.response.write_text(
		json.dumps({"lectures": lectures_out}, ensure_ascii=False, indent=1) + "\n",
		encoding="utf-8",
		newline="\n",
	)
	print(f"LLM response -> {args.response}; run `merge` to validate and apply")


# --------------------------------------------------------------------------
# Stage 3: merge (deterministic guardrails)
# --------------------------------------------------------------------------

def keyword_form_error(keyword: str) -> str | None:
	if has_cjk(keyword):
		return "contains CJK"
	if not has_ascii_letter(keyword):
		return "no English letters"
	if len(keyword) > MAX_KEYWORD_CHARS:
		return f"too long ({len(keyword)} > {MAX_KEYWORD_CHARS} chars)"
	if len(keyword.split()) > MAX_KEYWORD_WORDS:
		return f"too many words ({len(keyword.split())} > {MAX_KEYWORD_WORDS})"
	norm = normalize(keyword)
	if len(norm) < 3:
		return "too short"
	if norm in KEYWORD_STOPLIST:
		return "stoplisted generic term"
	words = norm.split()
	if words and all(w in KEYWORD_FRAGMENTS for w in words):
		return "function-word fragment"
	if re.fullmatch(r"[\W\d_]+", keyword):
		return "pure symbols"
	return None


def _loose(s: str) -> str:
	"""Alphanumeric-only form, tolerant of LaTeX escapes like Schr\\"o."""
	return re.sub(r"[^0-9a-z]", "", s.lower())


def signal_matches_pool(cited_norm: str, pool_norms: list[str]) -> bool:
	if cited_norm in pool_norms:
		return True
	for cand in pool_norms:
		if len(cited_norm) >= MIN_SIGNAL_MATCH_LEN and cited_norm in cand:
			return True
		if len(cand) >= MIN_SIGNAL_MATCH_LEN and cand in cited_norm:
			return True
	# loose fallback: pool texts may carry LaTeX escapes (e.g. Schr\"o -> o)
	loose_cited = _loose(cited_norm)
	if len(loose_cited) >= MIN_SIGNAL_MATCH_LEN:
		for cand in pool_norms:
			loose_cand = _loose(cand)
			if loose_cited in loose_cand:
				return True
			if len(loose_cand) >= MIN_SIGNAL_MATCH_LEN and loose_cand in loose_cited:
				return True
	return False


def validate_lecture(entry: dict, lecture: dict) -> tuple[list[dict], list[str]]:
	"""Return (accepted keywords, warnings) for one lecture entry."""
	pool_norms = [c["norm"] for c in lecture["candidates"]]
	warnings: list[str] = []
	accepted: list[dict] = []
	seen: set[str] = set()

	raw_keywords = entry.get("keywords")
	if not isinstance(raw_keywords, list) or not raw_keywords:
		return [], [f"{lecture['lecture']}: no keywords"]
	if len(raw_keywords) > MAX_KEYWORDS:
		warnings.append(f"{lecture['lecture']}: {len(raw_keywords)} keywords > {MAX_KEYWORDS}, truncating")

	for item in raw_keywords[:MAX_KEYWORDS]:
		if not isinstance(item, dict):
			warnings.append(f"{lecture['lecture']}: malformed keyword entry {item!r}")
			continue
		en = str(item.get("en", "")).strip()
		refs = item.get("from") or []
		if not isinstance(refs, list):
			refs = [refs]

		err = keyword_form_error(en)
		if err:
			warnings.append(f"{lecture['lecture']}: reject {en!r} ({err})")
			continue

		norm = normalize(en)
		if norm in seen:
			warnings.append(f"{lecture['lecture']}: reject {en!r} (duplicate within lecture)")
			continue

		cited = [normalize(str(r)) for r in refs if str(r).strip()]
		if not cited:
			warnings.append(f"{lecture['lecture']}: reject {en!r} (no provenance signal)")
			continue
		if not any(signal_matches_pool(c, pool_norms) for c in cited):
			warnings.append(f"{lecture['lecture']}: reject {en!r} (provenance not in candidate pool: {refs})")
			continue

		seen.add(norm)
		accepted.append({"en": en, "from": [str(r) for r in refs]})

	if not accepted:
		warnings.append(f"{lecture['lecture']}: no valid keywords survived validation")
	return accepted, warnings


def lecture_sort_key(name: str) -> tuple[int, str]:
	m = re.match(r"^(\d+)-", name)
	return (int(m.group(1)), name) if m else (10**9, name)


def cmd_merge(args: argparse.Namespace) -> None:
	candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
	by_lecture = {e["lecture"]: e for e in candidates["lectures"]}
	response = json.loads(args.response.read_text(encoding="utf-8"))
	entries = response.get("lectures", response if isinstance(response, list) else [])
	if isinstance(entries, dict):
		entries = [entries]

	existing: dict[str, object] = {}
	if args.topics.exists():
		existing = json.loads(args.topics.read_text(encoding="utf-8"))

	new_topics: dict[str, object] = {}
	warnings: list[str] = []
	for entry in entries:
		name = str(entry.get("lecture", "")).strip()
		if name not in by_lecture:
			warnings.append(f"unknown lecture {name!r} (not discovered with both PDFs); skipped")
			continue
		accepted, warns = validate_lecture(entry, by_lecture[name])
		warnings.extend(warns)
		if accepted:
			new_topics[name] = [k["en"] for k in accepted]

	# incremental: lectures absent from the response keep their current entry
	for name, keywords in existing.items():
		if name.startswith("_"):
			continue
		if name not in new_topics:
			new_topics[name] = keywords

	if args.strict and warnings:
		for w in warnings:
			print(f"strict-mode violation: {w}")
		raise SystemExit(1)

	ordered: dict[str, object] = {
		"_comment": (
			"lecture folder name -> English keywords (max 5 each), rendered in the "
			"知识点 column of README.md. Curated via ai/lectures/extract_topics.py "
			"(harvest -> LLM curate -> validate/merge); keys starting with '_' are metadata."
		),
	}
	for name in sorted(new_topics, key=lecture_sort_key):
		ordered[name] = new_topics[name]

	args.topics.write_text(
		json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
	)
	for w in warnings:
		print(f"warning: {w}")
	print(f"merged {len(new_topics)} lectures -> {args.topics}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="LLM-centric knowledge-point extraction pipeline")
	parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
	parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
	parser.add_argument("--response", type=Path, default=DEFAULT_RESPONSE)
	parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
	parser.add_argument("--top", type=int, default=50, help="emphasized candidates shown per lecture in the packet")
	parser.add_argument("--top-structural", type=int, default=80, help="structural candidates (theorem titles etc.) shown per lecture")
	sub = parser.add_subparsers(dest="command", required=True)

	sub.add_parser("harvest", help="scan .tex sources and write the raw candidate pool")

	sub.add_parser("pack", help="render the LLM prompt packet")

	curate = sub.add_parser("curate", help="run the LLM curation stage")
	curate.add_argument("--llm", choices=["packet", "api"], default="packet")
	curate.add_argument("--retries", type=int, default=2)

	merge = sub.add_parser("merge", help="validate the LLM response and merge into topics.json")
	merge.add_argument("--strict", action="store_true", help="fail on any validation warning")

	args = parser.parse_args()
	args.candidates = args.candidates.resolve()
	args.prompt = args.prompt.resolve()
	args.response = args.response.resolve()
	args.topics = args.topics.resolve()
	return args


def main() -> None:
	args = parse_args()
	{
		"harvest": cmd_harvest,
		"pack": cmd_pack,
		"curate": cmd_curate,
		"merge": cmd_merge,
	}[args.command](args)


if __name__ == "__main__":
	main()
