# weekly

用于维护仓库根目录 [README.md](../../README.md) 中的 `## 周历` 表格，并增量维护录屏映射数据。

## 目录说明

- [weekly.py](weekly.py)
	- 主脚本，纯标准库实现（`argparse` / `json` / `re` / `urllib` / `datetime` / `pathlib`），无第三方依赖。
	- 一次运行可做两件事：
		1. 从 B 站录屏合集**增量同步** [recordings_by_lecture.json](recordings_by_lecture.json)（按 `bvid` 去重并追加）；
		2. 根据 [recordings_by_lecture.json](recordings_by_lecture.json) **重新生成**根 README.md 的 `## 周历` 表格（按实际上课日期一行一条日期）。
- [recordings_by_lecture.json](recordings_by_lecture.json)
	- 录屏映射数据源。
	- 结构：`lecture -> [{"bvid": "BV...", "date": "YYYY-MM-DD"}, ...]`。
	- `date` 是视频标题中 `YYYYMMDD` 前缀对应的实际上课日期，不是上传日期。
	- 以 `_` 开头的键（`_comment`、`_week_start`）为元数据，不参与表格生成。
- [prompt.md](prompt.md)
	- 该目录任务的提示词说明（周历的格式规则与自动化要求）。
- [README.md](README.md)
	- 本文件。

## 数据源

1. **B 站录屏合集**：https://space.bilibili.com/479141149/lists/7582381
	- 脚本通过 B 站 open API `x/polymer/web-space/seasons_archives_list` 分页拉取合集内全部视频（`page_size=100`，逐页翻到底）。
	- 默认参数：`mid = 479141149`，`season_id = 7582381`，可用 `--playlist-mid` / `--season-id` 覆盖。
	- API 需要登录态时可传 `--cookie`（如 `SESSDATA=...; bili_jct=...`）。
2. **本地映射**：[recordings_by_lecture.json](recordings_by_lecture.json)
	- 同步的落点与表格生成的数据源；即使不连 B 站，也能仅依据本地 JSON 重建周历。

## 标题解析规则

合集视频标题需同时包含：

- `YYYYMMDD` 形式的日期（正则 `\b(20\d{6})\b`，取上课日期，非上传日期）；
- `math4cs-<序号>-` 形式的讲次标记（正则 `(?:^|-)math4cs-(\d+)-`，大小写不敏感）。

脚本用讲次序号到仓库根目录匹配课件目录名（如 `1` → `1-prop-logic`），解析为 `(lecture, date)`；标题不符合任一规则、或讲次目录不存在的视频会被跳过。

## 增量合并规则（bvid 为唯一键）

- 已存在的 `bvid`：保持原顺序不变；若旧记录缺 `date` 而本次解析到日期，则补齐日期。
- 新 `bvid`：追加到对应 lecture 列表末尾。
- 合并后按讲次序号排序写回 JSON，并维护 `_comment` / `_week_start` 元数据键。
- 同一 lecture 内录屏的编号 `(N)` 即其在 JSON 列表中的顺序（从 1 开始），多次运行结果稳定。

## 周历生成规则

- 周次计算：`week = (date - week_start).days // 7 + 1`，默认 `week_start = 2026-03-02`（第一周周一），可用 `--week-start` 覆盖。
- 同一日期多条录屏合并到同一行；行内多条链接以 `; ` 分隔。
- 所有行按日期升序排列。

## 周历输出格式

脚本会在仓库根目录 [README.md](../../README.md) 的 `## 周历` 段落生成如下格式：

| 周次 | 日期 | 课堂录屏 |
| :---: | :---: | :---: |

链接格式：`[lecture-(N)](https://www.bilibili.com/video/BV.../)`，例如：

```
| 1 | 2026-03-03 | [0-overview-(1)](https://www.bilibili.com/video/BV1kTAozRE8c/); [0-overview-(2)](https://www.bilibili.com/video/BV1CKAozxEVA/) |
```

## 输入 / 输出

| 类型 | 内容 |
| :--- | :--- |
| 输入 | B 站合集 API（或 `--archives-json` 指定的本地导出文件）、本地 [recordings_by_lecture.json](recordings_by_lecture.json)、仓库根目录的课件目录名 |
| 输出 | 更新后的 [recordings_by_lecture.json](recordings_by_lecture.json)（除非 `--dry-run` / `--no-sync-recordings`）、根目录 [README.md](../../README.md) 的 `## 周历` 表格（除非 `--dry-run`） |

## 运行方式

在仓库根目录执行：

```bash
python ai/weekly/weekly.py
```

上面命令会：

1. 从 B 站合集 API 拉取录屏列表并增量更新 [recordings_by_lecture.json](recordings_by_lecture.json)
2. 更新根目录 [README.md](../../README.md) 的 `## 周历` 区块

成功时打印 `Updated weekly schedule in <readme路径>`。

## 常用命令

仅预览周历，不写文件（仍会尝试连接 B 站，可用 `--no-sync-recordings` 彻底离线）：

```bash
python ai/weekly/weekly.py --dry-run
```

只生成周历，不同步远端录屏（使用当前本地 JSON）：

```bash
python ai/weekly/weekly.py --no-sync-recordings
```

API 受限时，可使用已导出的 archives JSON（支持 `[...]`、`{"archives": [...]}`、`{"data": {"archives": [...]}}` 三种结构）：

```bash
python ai/weekly/weekly.py --archives-json path/to/archives.json
```

如需附带 Cookie 请求 API：

```bash
python ai/weekly/weekly.py --cookie "SESSDATA=...; bili_jct=..."
```

## 命令行参数

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `--repo-root` | `Path(__file__).resolve().parents[2]` | 仓库根目录路径 |
| `--readme` | `<repo-root>/README.md` | 目标 README.md 路径 |
| `--recordings-map` | `<repo-root>/ai/weekly/recordings_by_lecture.json` | 录屏映射 JSON 路径 |
| `--week-start` | `2026-03-02` | 第一周周一（YYYY-MM-DD） |
| `--dry-run` | 关闭 | 只打印周历表格到 stdout，不写任何文件 |
| `--no-sync-recordings` | 关闭 | 跳过 B 站同步，仅用本地 JSON 生成周历 |
| `--archives-json` | 无 | 本地 archives JSON 文件路径（替代 API 拉取） |
| `--playlist-mid` | `479141149` | B 站上传者 mid |
| `--season-id` | `7582381` | B 站合集 season_id |
| `--cookie` | 空 | 请求 B 站 API 时附带的 Cookie |
| `--strict-sync` | 关闭 | 同步失败立即报错退出；默认行为见下 |
| `--status-log` | 无 | 每次运行向该文件追加一行带时间戳的状态记录 |

## 错误处理

默认情况下，如果远端同步失败（例如风控返回 `-352`、网络超时），脚本会打印 `Warning: recordings sync skipped due to error: ...` 并继续使用本地 [recordings_by_lecture.json](recordings_by_lecture.json) 生成周历。若希望同步失败即报错退出：

```bash
python ai/weekly/weekly.py --strict-sync
```

## 同步状态标志（SYNC_STATUS）

B 站风控（`-352`）是**间歇性**的：同一命令可能这次失败、下次成功。因此每次运行结束时，脚本都会输出一行机器可判定的状态标志，供自动化流程区分「降级重建」与「真正同步成功」：

| 状态 | 含义 |
| :--- | :--- |
| `SYNC_STATUS: ok` | 远端同步真正完成，[recordings_by_lecture.json](recordings_by_lecture.json) 已按远端数据更新 |
| `SYNC_STATUS: degraded (...)` | 远端同步失败（如 `-352` 风控），周历是基于本地 JSON 的降级重建，**未同步任何远端数据** |
| `SYNC_STATUS: skipped` | 未尝试远端同步（`--no-sync-recordings` 或 `--dry-run`） |

配合 `--status-log <文件>` 使用时，每次运行还会向该文件追加一行 `<ISO 时间戳>\t<状态>` 记录（该文件已列入 `.gitignore`），便于审计历史运行：

```bash
python ai/weekly/weekly.py --status-log ai/weekly/sync-status.log
```

## 自动重试定时任务

因风控可能持续数小时至数天，仓库配有定时任务（WorkBuddy automation，每 30 分钟一次）自动重跑上述同步流程：

- 每次运行执行 `python ai/weekly/weekly.py --status-log ai/weekly/sync-status.log` 并检查 `SYNC_STATUS`；
- 仅为 `degraded` / `skipped` 时什么都不做，等待下次重试；
- 只有出现 `SYNC_STATUS: ok`（真正完成远端同步）时，才提交 `recordings_by_lecture.json` 与 `README.md` 的改动、`git push`，并**自动删除该定时任务**（一次性达成即退场）。

手动触发时照常运行脚本即可，无需等待定时任务。

## 增量更新说明

- 脚本以 `bvid` 为唯一键进行合并：
	- 已存在 `bvid`：保持原顺序；若旧记录无日期且新解析到日期，则补齐日期。
	- 新 `bvid`：追加到对应 lecture 列表末尾。
- 每次运行后，同一 lecture 的编号 `(N)` 会按其在 JSON 中的顺序稳定生成。
- 典型工作流：每讲录屏上传 B 站合集 → 运行 `python ai/weekly/weekly.py` → 提交 README.md 与 JSON 的改动。
