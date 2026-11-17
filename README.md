# Reverse Fusion Next：Reverse方法＋增强REA

用白话提出目标，智能体根据证据自主选工具和顺序。本项目提供可选的专业方法、REA工具、任务记忆、验证/外部结果审查和空间管理，不要求每项任务都使用我们的流程。普通开发保持原生；调查、观察和实现可交替，纯分析可只交报告。

本版为独立项目 [reverse-fusion-next](https://github.com/gthubtom1/reverse-fusion-next)，基于1.4.0提交`022e61b803e41569cac1f116ebca2245b9c9b1f8`。旧项目和基线保留。实际资格及本机切换见[当前状态](docs/CURRENT-STATE.md)。

最终形态采用“REA核心＋按需Reverse＋薄适配层”。本轮通过GitHub预发布交付静态校验源码快照，**当前源码运行未验，暂不部署或切换本机入口**；发布状态及范围见[发布记录](docs/NEXT/PUBLICATION.md)，实现见[最终形态](docs/NEXT/FINAL-FORM.md)。

- 官方REA：保留原工具、专业结果、bundle、未知项和验证语义。
- Reverse：按当前问题检索专业方法，不默认加载整套阶段/workitem控制规则。
- 自有薄层：按需保存完整要求和恢复点，提供原生/Windows/网页检查及独立标注的外部证据宿主审查。readiness只诊断验收，不限制宿主调查或编辑；旧接口兼容。交付区分独立重写、按规格实现、分析和修改原程序，不自动替换用户目标。

当前宿主负责推理、原生编码和构建。参考Craft的有界比较/修正思路后独立实现，Craft无需安装或运行；Spec可选。没有第二个模型循环。

2.2.0补充长任务机制：观察快照、紧凑状态与行动诊断、可选的实际脚本计量/复用、候选产品身份核对。
宿主仍直接使用工具，不要求每次修改都截图或打包；验证随变化选择。具体发现与结论见
[长任务复核](docs/NEXT/LONG-TASK-CONCLUSIONS.md)。这些工程改进不等于已证明模型速度或成功率优于同模型同工具的原生宿主。

2.4.0扩展[磁盘生命周期](docs/DISK-MANAGEMENT.md)：文件生成时区分必须保留、可能复用、用完即删，
操作或验证结束时审查清理；缓存复用先核输入与内容，持久资料保持保护。
每项目临时预算、跨项目按卷预留和连接内周期维护继续保留；历史未登记目录保持原样。
架构的帮助、成本和困难目标能力依据见[本轮复核](docs/NEXT/ARCHITECTURE-REVIEW.md)。

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
