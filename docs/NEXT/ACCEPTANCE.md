> 此文件下方为上一轮2.0.0有限验收，正在被2.1.0最终复核取代。当前状态以FINAL-AUDIT和STATUS为准。

# 独立改版最终验收

本轮定义的20项工程要求均有对应证据。范围是Windows x64 / Codex；它说明本版完整工程与安装可用，不代表任意目标已经复刻成功。

| ID | 要求 | 结果 | 依据与实际意义 |
|---|---|---|---|
| N01 | 独立目录与旧版保全 | 已验收 | 独立Git对象、冻结基线；原仓库HEAD和工作区保持原样。 见 `baseline/identity.json`。 |
| N02 | 持久需求、计划与恢复 | 已验收 | 每阶段记录实际证据，压缩后按RESUME与唯一下一步恢复。 见 `docs/NEXT/REQUIREMENTS.md`。 |
| N03 | Reverse多领域保留 | 已验收 | 603个方法/支撑文件按来源与适配摘要核对，45路由可用、192原路由例子通过；普通开发不建逆向case。 见 `components/reverse-core/preservation.json`。 |
| N04 | 真实官方REA | 已验收 | 固定官方6.9.0，真实Ghidra分析，自有PE原生记录导出后新进程原样导入。 见 `evidence/next/s2/native-live.json`。 |
| N05 | 增强REA单入口 | 已验收 | 保留255原工具schema与prompts，增加4个独立标识工具，宿主唯一推理者。 见 `evidence/next/s2/protocol-qualified.json`。 |
| N06 | Craft零运行依赖 | 已验收 | 排除Craft源码/二进制的提交导出仍完成全新安装、实际工具连接和独立检查。 见 `evidence/next/s5/clean-install.json`。 |
| N07 | Spec不强制 | 已验收 | 没有Spec仍完成依据、宿主实现、比较、修正与恢复。 见 `evidence/next/s1/vertical.json`。 |
| N08 | 白话与完整目标保持 | 已验收 | 原话/补充和继续同case得到检查；有限切片不改完整目标。 见 `tests_next/test_workflow.py`。 |
| N09 | 证据驱动方法选择 | 已验收 | 领域按证据细化；有无账号、壳和反调试作为调查条件，避免固定绕过/调试/dump路线；选择由当前宿主负责。 见 `docs/AGENT-WORKFLOW.md`。 |
| N10 | 单case与原生来源 | 已验收 | 需求、依赖、证据与检查在同case，原REA记录单独保持官方身份并以文件引用。 见 `rea_enhanced/workflow.py`。 |
| N11 | 实现依据与相关阻断 | 已验收 | 校验已声明依据与关键未知依赖；只有受影响功能阻断，语义审查仍由宿主负责。 见 `tests_next/test_workflow.py`。 |
| N12 | 宿主原生实现 | 已验收 | 宿主实际编辑错误候选并修正，构建/运行与比较真实执行，无第二模型或假Craft引擎。 见 `evidence/next/s1/vertical.json`。 |
| N13 | 独立行为与状态比较 | 已验收 | 两侧独立运行，顺序状态、输出、退出与文件字节比较；同源对照和空观察拒绝。 见 `evidence/next/s1/vertical.json`。 |
| N14 | 视觉与行为分开 | 已验收 | 实际浏览器两种宽度；行为错误与仅颜色错误分别识别，保留截图/DOM/指定存储。 见 `evidence/next/s3/web/qualification.json`。 |
| N15 | 失败反馈与失效 | 已验收 | 代码/计划/证据/比较器变化使旧通过失效；不变通过复用，失败重试需新信息并有预算。 见 `tests_next/test_workflow.py`。 |
| N16 | 边界、取消与清理 | 已验收 | 路径、档案、时间/内存/输出、取消和并发反例通过；自有进程清理实测，不冒称OS隔离。 见 `tests_next/test_mcp.py`。 |
| N17 | 真实依赖与工具索引 | 已验收 | 独立Node Frida绑定实际枚举；缺绑定判不完整，安装生成当前路径索引，路径与操作资格分开。 见 `components/rea-enhanced/provider-bindings.json`。 |
| N18 | 冻结基线对照 | 已验收 | 相同自有输入正确/错误候选在新旧都得到正确结果；新文件通道单独记录，不宣称模型A/B胜出。 见 `evidence/next/s5/baseline-comparison.json`。 |
| N19 | 安装、迁移与回退 | 已验收 | 新目录独立下载运行包；实际本机切换→完整恢复原入口并连接旧两项工具→再选新版；无关字节保留，支持客户端丢注释形式。 见 `evidence/next/s5/clean-install.json`。 |
| N20 | 新机安装与零基础引导 | 已验收 | 唯一安装入口、明确分支、白话开场和恢复/回退，无需追加用户样本完成本版工程。 见 `docs/AGENT-BOOTSTRAP.md`。 |

最终源代码：53项检查通过、零跳过。最终提交导出：不含Craft/Spec源码或运行包，从零取得依赖、实际登记连接、41项独立检查及临时入口回退通过。
本机实际迁移与回退通过，旧仓库干净，无关配置字节不变。当前已登记增强REA 2.0.0，工具数259。原生REA证明与自有比较回执严格分开。

当前旧聊天未检索到新增工具，桌面热加载不在通过声明内；新建/重连聊天后才使用新登记。其它宿主和未选择的目标专用provider不冒称已实际运行。
需求/依赖遗漏仍依赖宿主审查，有限比较不是全程序等价或操作系统隔离；完整目标与剩余工作必须在每个实际case继续核对。
完整证据映射见ACCEPTANCE.json，实际回退回执路径在evidence/next/s6/local-migration.json，本地恢复数据只在state中，不包含无关配置备份。
