请更新 `math4cs-lectures/README.md` 的 `周历`，并保证可持续增量维护。

数据源：

1. B 站录屏合集：https://space.bilibili.com/479141149/lists/7582381
2. 本地映射：`ai/weekly/recordings_by_lecture.json`

输出格式：

| 周次 | 日期 | 课堂录屏 |
| :---: | :---: | :---: |

规则：

1. 每一行对应一个实际上课日期（按日期升序）
2. 周次计算：以 `2026-03-02` 为第一周周一，`week = (date - 2026-03-02).days // 7 + 1`
3. 同一日期多条录屏时，合并到同一行；链接格式：`[lecture-(N)](https://www.bilibili.com/video/BV.../)`
4. `N` 为该 lecture 在 `recordings_by_lecture.json` 列表中的顺序编号（从 1 开始）

自动化要求：

1. 使用 `ai/weekly/weekly.py` 自动完成更新
2. 脚本应支持从 B 站合集增量同步到 `recordings_by_lecture.json`（按 `bvid` 去重）
3. 脚本应兼容已有 JSON，允许继续迭代补充新录屏后自动更新周历