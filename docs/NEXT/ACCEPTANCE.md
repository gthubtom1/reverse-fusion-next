# Reverse Fusion Next 2.1.0 历史工程验收

本表保留当时有限工程资格，不代表2.2.0长任务修复已通过。当前结论见STATUS.json、
LONG-TASK-REPAIR.md与LONG-TASK-CONCLUSIONS.md；本轮源码变化后由release-check核对新资格。

本轮20项工程要求已逐项验收，并完成独立项目发布、本机清洁部署及真实白话任务。
旧版反复漏检的经验与16类审查发现见FINAL-AUDIT.md；失败反例、修复前记录及实际操作保留。

| ID | 要求 | 结果 | 当前依据与意义 |
|---|---|---|---|
| N01 | 独立目录与旧版保全 | 已验收 | 独立GitHub仓库main为唯一新版入口；旧master基线保留，误发旧分支已归档后移除。 见 `evidence/next/final-audit/remote-install.json`。 |
| N02 | 持久需求、计划与恢复 | 已验收 | 每阶段记录实际证据，压缩后按RESUME与唯一下一步恢复。 见 `docs/NEXT/REQUIREMENTS.md`。 |
| N03 | Reverse多领域保留 | 已验收 | 603个方法/支撑文件按来源与适配摘要核对，45路由可用、192原路由例子通过；普通开发不建逆向case。 见 `components/reverse-core/preservation.json`。 |
| N04 | 真实官方REA | 已验收 | 当前代码实际Ghidra分析自有PE，原生bundle在新进程导入后记录一致；全REA原包逐文件认证。 见 `evidence/next/final-audit/native-provider.json`。 |
| N05 | 增强REA单入口 | 已验收 | 本机Codex直接调用增强状态与原REA；一个登记包含255原工具和4增强工具，原schema/prompts保持。 见 `evidence/next/final-audit/desktop-entry.json`。 |
| N06 | Craft零运行依赖 | 已验收 | 排除Craft源码/二进制的提交导出仍完成全新安装、实际工具连接和独立检查。 见 `evidence/next/s5/clean-install.json`。 |
| N07 | Spec不强制 | 已验收 | 没有Spec仍完成依据、宿主实现、比较、修正与恢复。 见 `evidence/next/s1/vertical.json`。 |
| N08 | 白话与完整目标保持 | 已验收 | 不同目标返回明确上下文冲突；带新要求继续自动保存；真实白话聊天保留原话和补充至最终交付。 见 `tests_next/test_final_audit.py`。 |
| N09 | 证据驱动方法选择 | 已验收 | 领域按证据细化；有无账号、壳和反调试作为调查条件，避免固定绕过/调试/dump路线；选择由当前宿主负责。 见 `docs/AGENT-WORKFLOW.md`。 |
| N10 | 单case与原生来源 | 已验收 | 同case保存原话、补充、功能、证据、unknown、实际比较、覆盖审查和交付；原REA bundle单独保留。 见 `evidence/next/final-audit/plain-host.json`。 |
| N11 | 实现依据与相关阻断 | 已验收 | unknown解决绑定证据快照，替换证据/降为推断重新阻断；关键未知必须明确影响范围；依赖闭包变化使旧比较失效。 见 `tests_next/test_final_audit.py`。 |
| N12 | 宿主原生实现 | 已验收 | 新白话Codex聊天实际分析、宿主编写独立实现、运行与修正，最终交付源码和启动入口。 见 `evidence/next/final-audit/plain-host.json`。 |
| N13 | 独立行为与状态比较 | 已验收 | 有限独立进程/状态比较，实际调用声明源码；外部运行器/实际启动环境绑定，同外部脚本拒绝。 见 `evidence/next/final-audit/plain-host/core-comparison.json`。 |
| N14 | 视觉与行为分开 | 已验收 | 真实浏览器独立报告视觉与行为；通用下拉/勾选/确认框/存储状态操作，错误及缺失观察反例。 见 `evidence/next/final-audit/web-controls.json`。 |
| N15 | 失败反馈与失效 | 已验收 | 回执摘要、运行器、环境、来源、依赖、计划及比较器变化失效；复用返回原路径，失败重试有新信息与预算。 见 `tests_next/test_final_audit.py`。 |
| N16 | 边界、取消与清理 | 已验收 | 进程边界/取消/清理与中断记录；共享依赖图存平面闭包避免指数放大；旧连接发现运行代码变化即拒绝增强操作。 见 `tests_next/test_mcp.py`。 |
| N17 | 真实依赖与工具索引 | 已验收 | 固定REA全包与独立Frida加载/枚举，保存provider路径，实际Ghidra操作；未选provider不冒称全部可用。 见 `evidence/next/final-audit/native-provider.json`。 |
| N18 | 冻结基线对照 | 已验收 | 相同自有输入正确/错误候选在新旧都得到正确结果；新文件通道单独记录，不宣称模型A/B胜出。 见 `evidence/next/s5/baseline-comparison.json`。 |
| N19 | 安装、迁移与回退 | 已验收 | 实际旧后台退役为零，托管入口卸载→空登记→新装；无关字节保持，回退留存；孤立旧注释重装反例修复。 见 `evidence/next/final-audit/clean-redeployment.json`。 |
| N20 | 新机安装与零基础引导 | 已验收 | 独立项目默认入口真实clone、公共安装器独立下载、完整检查及临时用户回退；仅本机Windows环境，不冒称全新OS。 见 `evidence/next/final-audit/remote-install.json`。 |

本地固定源码81项检查通过；独立GitHub默认分支真实clone、全新checkout/venv/下载目录、
公开安装器和81项检查再次通过，临时用户回退准确。最终资格绑定当前代码、测试、公共合同及原操作摘要。
被资格确认的实现提交：`0eaa223e8da0f10dc41426163eb997b8b57a6208`；后续只写进度和证据不改变被确认实现。

实际本机卸载三项托管入口，确认空登记后重装；无关配置字节一致。旧目录90个启动器/子进程已退役，
新代码最终固定后缓存连接也已刷新；当前一个reverse-fusion-rea含255原工具与4增强工具，Craft不登记。
旧源码与原版运行包保留用于回退，保留文件不表示仍在Codex中启用。

白话新聊天在开发目录外完成自有离线软件的分析、REA观察、宿主实现、比较、修正、覆盖审查和交付。
实际比较5162项核心输入、60组网页观察、24组边界及8项启动检查；这些数字只描述本案例。
开发中更新导致旧连接缓存时，宿主识别差异并采用当前绝对CLI重核；最终新增连接身份门防止静默混用。
最终清洁重装之后，又一新聊天已实际调用增强入口，独立验证客户端加载。

工程通过不等于任意目标已经成功复刻。全部原话与补充需在每个case审查；困难壳、隐藏服务、设备和
其它宿主的结果不能从本案例推断。不是全新OS测试，也未做模型A/B；不恢复旧换肤目标或改变其授权。
