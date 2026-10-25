# lectures

维护仓库根目录 [README.md](../../README.md) 中的 `## 课件` 表格：自动发现已发布的课件目录，生成课件与讲义的下载链接表。

## 目录说明

- [lectures.py](lectures.py)
  - 唯一脚本，纯标准库实现（`argparse` / `re` / `pathlib`），无第三方依赖。
  - 扫描仓库根目录 → 过滤「课件 + 讲义双 PDF 齐全」的目录 → 生成表格 → 原地替换根 README.md 的 `## 课件` 段落。
  - 可重复执行且幂等：内容无变化时重写结果与原文一致。

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

| 序号 | 课件 |
| :---: | :---: |

每行由分号分隔的两个相对链接组成，例如：

```
| 1 | [1-prop-logic](/1-prop-logic/1-prop-logic.pdf); [1-prop-logic-handout](/1-prop-logic/1-prop-logic-handout.pdf) |
```

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
| `--dry-run` | 关闭 | 只把表格打印到 stdout，不写 README.md |

## 增量维护流程

1. 新建课件目录（如 `16-xxx/`），编译产出 `16-xxx.pdf` 与 `16-xxx-handout.pdf` 并放入该目录；
2. 在仓库根目录运行 `python ai/lectures/lectures.py`；
3. 根 README.md 的 `## 课件` 表格自动刷新，新课件出现在对应序号行。

注意：只有课件与讲义**两个 PDF 都就绪**后目录才会出现在表格中；若只想让某一讲暂不露出，移除任一 PDF 再重跑即可。
