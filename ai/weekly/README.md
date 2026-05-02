# weekly

用于维护仓库根目录 [README.md](../../README.md) 中的 `周历` 表格，并增量维护录屏映射数据。

## 目录说明

- [weekly.py](weekly.py)
	- 主脚本。
	- 功能 1：从 B 站合集增量同步 `recordings_by_lecture.json`（按 `bvid` 去重并追加）。
	- 功能 2：根据 `recordings_by_lecture.json` 生成 `周历`（按实际上课日期一行一条日期）。
- [recordings_by_lecture.json](recordings_by_lecture.json)
	- 录屏映射数据源。
	- 结构：`lecture -> [{"bvid": "BV...", "date": "YYYY-MM-DD"}, ...]`。
	- `date` 是视频标题中 `YYYYMMDD` 前缀对应的实际上课日期，不是上传日期。
- [prompt.md](prompt.md)
	- 该目录任务的提示词说明。

## 周历输出格式

脚本会在仓库根目录 [README.md](../../README.md) 的 `## 周历` 段落生成如下格式：

| 周次 | 日期 | 课堂录屏 |
| :---: | :---: | :---: |

其中周次按第一周周一计算：

- `week = (date - week_start).days // 7 + 1`
- 默认 `week_start = 2026-03-02`

## 常用命令

在仓库根目录执行：

```bash
python ai/weekly/weekly.py
```

上面命令会：

1. 从 B 站合集 API 拉取录屏列表并增量更新 [recordings_by_lecture.json](recordings_by_lecture.json)
2. 更新根目录 [README.md](../../README.md) 的 `周历` 区块

仅预览周历，不写文件：

```bash
python ai/weekly/weekly.py --dry-run
```

只生成周历，不同步远端录屏（使用当前本地 JSON）：

```bash
python ai/weekly/weekly.py --no-sync-recordings
```

API 受限时，可使用已导出的 archives JSON：

```bash
python ai/weekly/weekly.py --archives-json path/to/archives.json
```

如需附带 Cookie 请求 API：

```bash
python ai/weekly/weekly.py --cookie "SESSDATA=...; bili_jct=..."
```

默认情况下，如果远端同步失败（例如风控返回 `-352`），脚本会打印 warning 并继续使用本地
[recordings_by_lecture.json](recordings_by_lecture.json) 生成周历。若希望同步失败即报错退出：

```bash
python ai/weekly/weekly.py --strict-sync
```

## 增量更新说明

- 脚本以 `bvid` 为唯一键进行合并：
	- 已存在 `bvid`：保持原顺序；若旧记录无日期且新解析到日期，则补齐日期。
	- 新 `bvid`：追加到对应 lecture 列表末尾。
- 每次运行后，同一 lecture 的编号 `(N)` 会按其在 JSON 中的顺序稳定生成。
