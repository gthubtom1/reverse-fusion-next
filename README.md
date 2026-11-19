# Reverse Fusion

告诉平常用的助手材料在哪、想拿到什么，例如：「对照这两份发布物，说明确认了哪些差异，哪些还不知道。」助手可以按问题选择工具，不用记工具名或固定流程。

**当前源码是四方融合候选 `0.1.0-rc.3`，不是最终稳定版。** 同一个本地任务已跑通 Reverse 方法、官方 REA 证据、Flutter 专项分析，以及借鉴 Craft 的独立对照和修正复验。四个助手是否会在真实对话里自行选对方法、是否比未接入时做得更好，仍未验收。[功能实测与范围](docs/NEXT/FUSION-CANDIDATE.md)

## 隔离试用

在 Windows x64 上准备 Python 3.11 或更高版本和已配置的助手。从本仓库根目录运行对应命令。使用专用试用目录，不改日常安装。

| 助手 | 命令 |
|---|---|
| Codex | `python fusion.py setup codex --home "$env:LOCALAPPDATA\ReverseFusionTrial"` |
| Claude Code | `python fusion.py setup claude --home "$env:LOCALAPPDATA\ReverseFusionTrial"` |
| Pi | `python fusion.py setup pi --home "$env:LOCALAPPDATA\ReverseFusionTrial"` |
| OpenCode | `python fusion.py setup opencode --home "$env:LOCALAPPDATA\ReverseFusionTrial"`；Desktop 2.x 可加 `--opencode-version 2` |

安装结果给出试用配置位置。Claude Code 可用 `--plugin-dir` 指向结果中的 `skill` 目录。具体如何让客户端加载试用配置，见[试用说明](docs/NEXT/FUSION-CANDIDATE.md)。检查和移除分别用 `check` 和 `remove` 替代 `setup`，保留相同宿主、`--home` 和版本选项。工具从本仓库启动，需保留仓库目录。没有锁定依赖的本地归档时，首次准备需要网络。

## 各部分做什么

| 部分 | 在融合入口中承担的工作 |
|---|---|
| REA | 对本地材料用选定的官方工具取证；保留原生结果和证据档案。 |
| Reverse Skills | 提供有出处、可按需读取的专业方法。 |
| SEEP 方向专项 | 读取支持的 Flutter ARM64 库中类的归属，按文件指纹与官方 ELF 证据对应。 |
| Craft 思路的增强层 | 独立运行两份可信本地程序，保存差异并复验修正。没有 Craft 或 Spec 运行依赖。 |

老版 [Field 入口](field.py)保留给原来的离线读数和证据审阅，不是四方融合的安装命令。旧版本记录见[历史档案](docs/history/README.md)；维护从[活动文档清单](docs/ACTIVE-DOCUMENTS.json)和[当前状态](docs/NEXT/STATUS.json)进入。历史 ZIP、验收会话和安装回退记录不随本次源码提交。
