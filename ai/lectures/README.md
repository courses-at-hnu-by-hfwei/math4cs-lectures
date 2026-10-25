# lectures

维护仓库根目录 [README.md](../../README.md) 中的 `## 课件` 表格：自动发现已发布的课件目录，生成课件与讲义的下载链接表。

## 目录说明

- [lectures.py](lectures.py)
	- 唯一脚本，纯标准库实现（`argparse` / `json` / `re` / `pathlib`），无第三方依赖。
	- 扫描仓库根目录 → 过滤「课件 + 讲义双 PDF 齐全」的目录 → 生成表格 → 原地替换根 README.md 的 `## 课件` 段落。
	- 可重复执行且幂等：内容无变化时重写结果与原文一致。
- [topics.json](topics.json)
	- 「知识点」列的数据源：`课件目录名 -> 英文关键词列表`，每讲最多 5 个。
	- 由 [extract_topics.py](extract_topics.py) 流水线生成并经守卫验证后写入；也可手工编辑。
	- 新增讲次时为此补一条条目；缺失的条目在表格中渲染为 `—`。
	- 以 `_` 开头的键为元数据，不参与表格生成。
- [extract_topics.py](extract_topics.py)
	- 知识点提取流水线（详见下文「知识点提取流水线」）：规则只负责高召回取材，LLM 负责语义筛选，规则守卫负责质量底线。

## 工作原理

1. **发现**：遍历仓库根目录下所有子目录，保留名字匹配 `^(\d+)-` 的目录（如 `0-overview`、`1-prop-logic`），并提取前缀数字作为序号。
2. **过滤**：仅收录同时包含 `<目录名>.pdf` 与 `<目录名>-handout.pdf` 的目录——即课件与讲义均已产出。缺任何一个 PDF 的目录不会进入表格。
3. **排序**：按序号数字升序排列。
4. **替换**：定位根 README.md 中的 `## 课件` 标记，用新表格整体替换该段落（直至下一个 `## ` 级标题或文件结尾），段落之外的內容保持不变。

## 输入

- 仓库根目录下的课件目录及其中的 PDF 文件（文件系统扫描，无配置文件）。
- 根目录 [README.md](../../README.md)：必须已包含 `## 课件` 段落，否则脚本报错退出（`ValueError`）。
- 默认仓库根目录取脚本路径的 `parents[2]`（`ai/lectures/lectures.py` → 仓库根），可用 `--repo-root` 覆盖。

## 输出

根目录 [README.md](../../README.md) 的 `## 课件` 表格：

| 序号 | 课件 | 知识点 |
| :---: | :---: | :--- |

- 「课件」列由分号分隔的两个相对链接组成，例如：
  `[1-prop-logic](/1-prop-logic/1-prop-logic.pdf); [1-prop-logic-handout](/1-prop-logic/1-prop-logic-handout.pdf)`
- 「知识点」列取自 [topics.json](topics.json)，关键词以 `; ` 分隔；未收录的讲次显示 `—`。

## 运行方式

在仓库根目录执行：

```bash
python ai/lectures/lectures.py
```

成功时打印 `Updated lectures table in <readme路径>`。

仅预览生成的表格、不写文件：

```bash
python ai/lectures/lectures.py --dry-run
```

## 命令行参数

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `--repo-root` | `Path(__file__).resolve().parents[2]` | 仓库根目录路径 |
| `--readme` | `<repo-root>/README.md` | 目标 README.md 路径 |
| `--topics` | `ai/lectures/topics.json`（脚本同目录） | 知识点 JSON 路径 |
| `--dry-run` | 关闭 | 只把表格打印到 stdout，不写 README.md |

## 知识点提取流水线（extract_topics.py）

纯规则匹配会输出大量琐碎、无价值的知识点；纯 LLM 又不可复现。因此流水线按「不同信任模型」拆成三段：**规则只做高召回取材，LLM 做语义筛选与综合，规则守卫把质量关**。

```
讲义 .tex 源文件
   │
   ▼
[1] harvest  确定性取材（高召回，不做判断）
   扫描每讲「主 tex + 被实际 input 的 parts（含嵌套 input 的传递闭包）」，采集四类原始信号：
     - 强调宏跨度（\bfit 粗斜体、\red/\green/\blue/... 颜色高亮、\rbox/\gbox/\bbox/\pbox 彩色框）
     - 定理/定义/引理/推论/命题/公理的标题
     - 帧标题（\frametitle / \begin{frame}{...}）
     - 章节名（parts 文件名）
   归一化、计数后写入 topics_candidates.json；被注释掉或未被引用的草稿文件不参与。
   │
   ▼
[2] curate   LLM 语义筛选（流水线核心）
   每讲向 LLM 提供：讲次标题、章节结构、候选信号池（次数+来源+原文）。
   LLM 按既定质量准则挑选 ≤5 个英文关键词，并为每个关键词引用候选池中的真实信号（可溯源）。
   两种调用方式：
     A. 全自动：curate --llm api（OpenAI 兼容 API，凭证走环境变量
        LLM_BASE_URL / LLM_API_KEY / LLM_MODEL，temperature=0，JSON 输出）
     B. 人/Agent 在环：pack 生成自包含提示词包 topics_prompt.md，由任意 LLM 按
        同一 schema 回填 topics_response.json
   │
   ▼
[3] merge    确定性守卫（质量底线，硬规则）
   校验响应文件：数量 1–5；仅英文（无 CJK）；≤6 词且 ≤60 字符；过滤泛词停用表与
   功能词碎片（the/iff/not...）；讲内去重；可溯源（每个关键词引用的信号必须能在
   候选池中匹配到，含 LaTeX 转义宽松匹配）。
   通过后增量合并进 topics.json（响应中未出现的讲次保留原条目）。
   │
   ▼
[4] lectures.py 渲染「知识点」列
```

### 质量准则（LLM 筛选标准，按优先级）

1. **核心性**：只选主线知识点——被着重强调、独立成定理/定义、或贯穿多个章节的概念；顺带提及、例子、花絮一律不选。
2. **特异性**：优先具体的概念名/定理名/算法名/结构名（如 `Hall's Theorem`），避免泛词（math、graph、problem、method）。
3. **形态规范**：英文；1–6 个词；≤60 字符；禁止公式、变元名、碎片、文件名、URL、中文。
4. **合并去重**：同义/近义/上下位信号合并为一个关键词（如 `Four-Color Theorem` 与 `Brooks's Theorem` → `Four-Color & Brooks' Theorems`）。
5. **覆盖性**：关键词合起来覆盖该讲主要章节（对照 parts 列表），不遗漏主线、不凑数。
6. **数量**：每讲 1–5 个，不足 5 个不硬凑。
7. **可溯源**：每个关键词必须引用候选池中真实出现的信号。

### 运行方式

```bash
# 完整流水线（API 模式，需先 export LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）
python ai/lectures/extract_topics.py harvest
python ai/lectures/extract_topics.py curate --llm api
python ai/lectures/extract_topics.py merge --strict

# 人/Agent 在环模式
python ai/lectures/extract_topics.py harvest
python ai/lectures/extract_topics.py pack        # 生成 topics_prompt.md
# 将提示词包交给任意 LLM，按 schema 回填 topics_response.json
python ai/lectures/extract_topics.py merge --strict
python ai/lectures/lectures.py                   # 刷新根 README 表格
```

中间产物（`topics_candidates.json` / `topics_prompt.md` / `topics_response.json`）已列入 `.gitignore`，可随时重新生成；提交物只有 `topics.json`。

### 子命令与参数

| 子命令 | 说明 |
| :--- | :--- |
| `harvest` | 扫描讲义源，写候选信号池 |
| `pack` | 渲染 LLM 提示词包（含质量准则与每讲信号池） |
| `curate` | LLM 筛选：`--llm api` 全自动；默认 packet 模式（打印指引） |
| `merge` | 校验响应并增量合并进 `topics.json`；`--strict` 有任何违规即退出 |

常用参数：`--candidates/--prompt/--response/--topics`（各阶段文件路径）、`--top`（每讲展示的强调信号数，默认 50）、`--top-structural`（结构性强信号数，默认 80）。

## 增量维护流程

1. 新建课件目录（如 `16-xxx/`），编译产出 `16-xxx.pdf` 与 `16-xxx-handout.pdf` 并放入该目录；
2. 运行知识点提取流水线（见上）为新讲生成关键词并合并进 [topics.json](topics.json)——也可以直接手工补一条；
3. 在仓库根目录运行 `python ai/lectures/lectures.py`；
4. 根 README.md 的 `## 课件` 表格自动刷新，新课件出现在对应序号行。

注意：只有课件与讲义**两个 PDF 都就绪**后目录才会出现在表格中；若只想让某一讲暂不露出，移除任一 PDF 再重跑即可。
