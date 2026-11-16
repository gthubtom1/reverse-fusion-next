# 白话任务如何运行

当前架构：Reverse领域方法＋增强REA。当前智能体是唯一推理与编码者。Craft不运行，Spec不强制；功能依据、比较和失败修正仍保留。

1. 用用户原话打开或恢复同一成果case（rf_next_case_open或增强CLI open）。普通开发保持原生，不制造逆向case。补充用record supplement，保留完整原目标。
2. 读返回的领域技能、required_read_paths、同固定REA包官方技能与相关方法。工具仓库仅共享代码，目标、报告和成果留当前项目。新证据用同case refine_route。
3. 核身份/格式及静态材料；按证据选择动态、浏览器、设备或其他方法。卡密、壳和反调试不是固定路线。记录可观察范围和缺资料影响。需要人时用白话问具体问题，不让零基础用户选工具。
4. 调用原REA及实际provider，保存真实错误。调查结束前export_evidence_bundle到case，重启import原bundle；以native-rea-bundle evidence引用其文件。增强回执不冒充原生证明。
5. 每功能record feature（description/evidence/checks/dependencies/review），审查输入、输出、状态、错误和外部依赖，不能靠默认值补事实。critical unknown只阻断相关功能。先做可验证部分，保留全部剩余目标。
6. 当前宿主实际写入、构建、运行。按COMPARISON.md冻结计划，独立运行原版/候选，行为与视觉分开。只有实际compare可记结果，不能手填passed。失败带差异回实现/分析，证据不足保留unknown。
7. 相关修改使旧通过失效；不变通过复用，不变失败需新信息。默认每check 12次，可记理由调整预算。中断先status恢复，用新输出目录，不覆盖记录、不无限空转。
8. 逐项回看原话与补充，说明实际验证和缺口。finite-scope-verified只覆盖已声明检查，不能把全产品改成演示。纯分析可deliver_analysis交报告，无需构建或Spec。

操作见COMPARISON.md，安装见AGENT-BOOTSTRAP.md，恢复见RECOVERY.md。旧领域资料用于专业知识；旧Spec/Craft实现指令由本文件、根RULES和当前reconstruction技能取代。
