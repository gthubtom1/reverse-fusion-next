# Reverse Fusion Next：Reverse方法＋增强REA

用白话交给智能体：分析软件、APK或网站，保留完整目标，在证据足够时实现，再独立比较并修正。普通开发保持宿主原生流程，纯分析可以只交报告。

本版为独立项目 [reverse-fusion-next](https://github.com/gthubtom1/reverse-fusion-next)，基于1.4.0提交`022e61b803e41569cac1f116ebca2245b9c9b1f8`。旧项目和基线保留。实际资格及本机切换见[当前状态](docs/CURRENT-STATE.md)。

运行核心只有两部分：

- Reverse：保留多领域方法、路由及困难目标的按需参考资料。
- 增强REA：保留官方REA真实工具与原生证据，增加持久目标、功能依据、依赖/未知项、独立比较、失效检查和中断恢复。

当前宿主负责推理、原生编码和构建。参考Craft的有界比较/修正思路后独立实现，Craft无需安装或运行；Spec可选。没有第二个模型循环。

安装范围为Windows x64、Codex。将本版放在长期保留目录：

```powershell
git clone https://github.com/gthubtom1/reverse-fusion-next.git D:\Project\reverse-next
cd D:\Project\reverse-next
powershell -NoProfile -File .\scripts\install.ps1
```

需要Python 3.11+。迁移已有旧部署、隔离安装、工具发现、连接和回退均按[唯一安装入口](docs/AGENT-BOOTSTRAP.md)，不要运行历史四组件脚本。

安装后在自己的软件项目目录打开Codex，用白话提出要求即可。例如：“帮我分析这里的软件，再做出功能和使用效果一样的版本。我不懂技术，需要我操作时请说清楚。”用户无需选择专业路由或复制整套技能。共享工具目录要保留；成果与证据留在当前项目。

从[零基础指南](docs/BEGINNER-GUIDE.md)开始。智能体执行合同见[工作流程](docs/AGENT-WORKFLOW.md)，比较格式见[有限比较](docs/COMPARISON.md)，中断和回退见[恢复](docs/RECOVERY.md)。

开发的[完整需求](docs/NEXT/REQUIREMENTS.md)、[阶段计划](docs/NEXT/PLAN.md)、[决策](docs/NEXT/DECISIONS.md)、[实际进度](docs/NEXT/STATUS.json)和[恢复入口](docs/NEXT/RESUME.md)持久保存。当前公共文档以[活动清单](docs/ACTIVE-DOCUMENTS.json)为准。其他继承文档、旧检查点和历史案例用于追溯，不能恢复旧Spec/Craft必经流程。

工程检查与具体软件验收分别记录。有限进程/文件/状态、网页行为和视觉比较只证明实际执行的范围；未观察到的服务、设备或功能仍需对应证据。全目标核对不能由工具目录、截图或一次通过替代。
