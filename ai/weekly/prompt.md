请根据以下信息完善 `math4cs-lectures/README.md` 中的 `周历`：

1. 录屏来源：B 站课堂录屏合集 https://space.bilibili.com/479141149/lists/7582381
2. 数据文件：`ai/weekly/recordings_by_lecture.json`，其中每条录屏包含 `bvid` 与实际上课日期 `date`

目标周历格式：

| 周次 | 日期 | 课堂录屏 |
| :---: | :---: | :---: |

要求：

1. `周历` 每一行对应一个实际上课日期（按日期升序）
2. 周次按第一周周一 `2026-03-02` 计算：`week = (date - 2026-03-02).days // 7 + 1`
3. 同一天有多条录屏时，全部放在该行 `课堂录屏` 列，链接格式为 `[lecture-(N)](https://www.bilibili.com/video/BV.../)`
4. 支持后续增量更新：只需更新 `recordings_by_lecture.json`，重新运行脚本即可刷新 `README.md` 的 `周历`
5. 若有必要，请生成或更新 `ai/weekly/weekly.py` 自动完成上述任务