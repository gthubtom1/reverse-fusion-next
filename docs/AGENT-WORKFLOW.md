# 自主选路，严格核实成果

这是可选支持，不是必经流程。宿主按目标与信息缺口选工具和顺序；REA、Reverse、自有比较器不要求每项任务都用。已有可靠任务记录就继续用，无需重复case/workitem。静态、动态、设备观察和实现可交替，不规定先授权、先Dump或先复刻。

原生工具直接工作即可。需要跨天恢复时再用case：open的recording=skip不落账，case可显式保存普通任务，auto兼容旧行为。checkpoint只保存重要进展、证据指针和下一步，不要求先列完功能。原话、补充和剩余目标须可靠保留；readiness只诊断验收，不限制调查/编辑。

选用内部验收时，requirement声明来源、维度和检查；真实compare产生自动结果。原生bundle/ID不改写。外部专业工具、设备或项目结果用assessment保存原观察、对象/输入身份、范围、上下文及局限，由宿主审查；这条路径标host-reviewed，不写内部pass或官方proof。可用requirement evaluation=host-review接受这类审查，缺证据与未接入自动工具分别显示。

交付区分analysis-report、independent-reimplementation、specification-implementation、modified-original；output_goal从原话/补充映射允许类型。deliver保持旧自动门；deliver_reviewed另记宿主审查交付，允许阶段范围，剩余项保留。修补原程序不叫独立复刻；候选单测不叫原版等价。具体schema见COMPARISON.md。

只在有价值的批次保存/核对状态，不逐条工具打卡。按变化验证，复用不变证据，失败需新信息；缺依赖仅影响相关工作。方法按需查DOMAIN-METHODS.md，大输出按DISK-MANAGEMENT.md，恢复见RECOVERY.md，安装见AGENT-BOOTSTRAP.md。
