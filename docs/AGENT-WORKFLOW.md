# 白话任务如何运行

当前架构：Reverse领域方法＋增强REA。当前智能体是唯一推理与编码者。Craft不运行，Spec不强制；功能依据、比较和失败修正仍保留。

宿主保留直接选工具、分析和编码的自主权。工具用于回答具体问题，不按组件逐个打卡。
普通开发无需case；简单逆向任务只记录支撑结论所需的最少事实。复杂复刻按独立可观察行为拆功能，
不要把网络、OCR、页面、全部业务合并成一个长期阻塞大组。status的diagnostics是待审提示，不是新的固定路线。

1. 用用户原话打开或恢复同一成果case（rf_next_case_open或增强CLI open）。普通开发保持原生，不制造逆向case。补充用record supplement，保留完整原目标。
2. 读返回的领域技能、required_read_paths、同固定REA包官方技能与相关方法。工具仓库仅共享代码，目标、报告和成果留当前项目。新证据用同case refine_route。
3. 核身份/格式及静态材料；按证据选择动态、浏览器、设备或其他方法。卡密、壳和反调试不是固定路线。记录可观察范围和缺资料影响。需要人时用白话问具体问题，不让零基础用户选工具。
4. 调用原REA及实际provider，保存真实错误。调查结束前export_evidence_bundle到case，重启import原bundle；以native-rea-bundle evidence引用其文件。增强回执不冒充原生证明。
5. 每功能record feature（description/evidence/checks/dependencies/review），审查输入、输出、状态、错误和外部依赖，不能靠默认值补事实。critical unknown只阻断相关功能。先做可验证部分，保留全部剩余目标。
   新evidence默认保存内容寻址副本，source_path保留原工作文件位置；活的规格/源依赖显式retention=live。
   旧case不改写原证据；失效项由status列出，重核后新增/更新有据条目，不凭新摘要洗白历史结论。
6. 当前宿主实际写入、构建、运行。按COMPARISON.md冻结计划，独立运行原版/候选，行为与视觉分开。只有实际compare可记结果，不能手填passed。失败带差异回实现/分析，证据不足保留unknown。
7. 相关修改使旧通过失效；不变通过复用，不变失败需新信息。默认每check 12次，可记理由调整预算。中断先status恢复，用新输出目录，不覆盖记录、不无限空转。
   验证强度按改动选：后端先源码/接口回放，界面变化查对应路由/交互/完整滚动区域，打包和运行时变化或阶段集成才整包验证。
   不要求每次小改动重截原版/整包构建。可用record execute记录耗时脚本、输入和产物并复用；仍可直接用宿主工具。
   操作成功不是比较通过；外部报告是依据，不自填pass。连续工作后回看实际减少的功能差距，编辑/截图/测试数量不代替进展。
8. 逐项回看原话与每条补充，用record coverage持久保存需求→功能映射及语义审查。
   每条原话来源/补充和每个功能均须覆盖；有未实现要求则继续保留，不能改名关闭。
   所有声明检查新鲜通过、未知项解决且成果文件齐全后，record deliver保存实际交付。
   reviewed-delivery表示宿主审查后的声明范围交付，不是自动证明全程序等价。
   新补充、功能/证据/未知项/成果/比较变化会使相应审查或交付失效。
   finite-scope-verified只覆盖已声明检查，不能把全产品改成演示。
   复刻交付前record product声明候选和原版身份文件；交付核对候选未被原版替换。
   源码交付登记候选入口/核心源文件，二进制交付登记候选可执行文件；保留原资产可复用但不以共同资源文件充当产品身份。
   纯分析可deliver_analysis交报告，无需构建或Spec。

已有case收到不同目标时open返回needs-context并携带incoming_request；智能体为新目标
选择独立case_root，或明确把它作为当前目标的supplement，不可静默丢弃。
“继续，再增加……”自动保存完整补充；无歧义的“继续”保持原记录。
unknown影响整个调查时显式scope=case；未指明影响范围的关键未知不能悄悄放行。

操作见COMPARISON.md，安装见AGENT-BOOTSTRAP.md，恢复见RECOVERY.md。旧领域资料用于专业知识；旧Spec/Craft实现指令由本文件、根RULES和当前reconstruction技能取代。

大量文件操作先读DISK-MANAGEMENT.md。生成时以rf_next_storage区分persistent、reusable、
disposable及空间预算：原始输入、源码、当前成果和有效证据保存在持久路径；有明确后续用途的
可重建材料放二级，复用先核输入/内容；本轮临时执行副本放三级，所有使用者结束后complete。
在有意义的操作批次/验证结束、阶段切换、恢复或空间压力节点review，而非每条命令都记账。
宿主根据后续工作决定二级keep/release并说明理由；一级不降级，活动与引用保护始终优先。
比较逐场景回收执行副本，execute接管TEMP；宿主直接命令和原REA工具须将可重建大输出指向分配空间。
不能把任意旧work目录当作垃圾，也不能用反复整包复制填满磁盘。困难目标按具体证据选择方法，
工具接通与有限工程检查不等于任意壳/混淆/反调试目标均已验证，见NEXT/ARCHITECTURE-REVIEW.md。
