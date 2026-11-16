# 有限比较

CLI：open --project-root <absolute> --request <plain words>；status；record --change-file <JSON> --revision <current>；compare --project-root <absolute> --check-id C1 --plan plan.json --output work/round-1。MCP有等价操作，rf_next_case_record公布各操作完整schema。下列格式由智能体生成，零基础用户无需填写。

record的change使用以下结构（每次使用status返回的最新revision）：

```json
{"op":"supplement","text":"用户补充原话"}
{"op":"evidence","id":"E1","path":"work/observed.md","authority":"observed","description":"实际观察"}
{"op":"feature","id":"F1","description":"保存状态","evidence":["E1"],"checks":["C1"],"dependencies":[],"review":"输入、输出、状态、失败及外部依赖的具体结论"}
{"op":"unknown","id":"U1","question":"服务响应尚未观察","critical":true,"features":["F1"]}
{"op":"unknown","id":"U2","question":"整个目标身份待确认","critical":true,"features":[],"scope":"case"}
{"op":"resolve","id":"U1","evidence":["E1"]}
{"op":"refine_route","hint":"发现这是APK且有反调试"}
{"op":"deliver_analysis","report":"work/report.md","evidence":["E1"]}
{"op":"budget","max_checks_per_feature":15,"reason":"新增错误输入观察，需要额外比较"}
{"op":"coverage","requirements":[{"id":"R1","text":"原始要求对应的具体范围","source":"original","features":["F1"]}],"review":"逐句复核原话与所有补充，说明覆盖依据及边界"}
{"op":"deliver","summary":"具体成果与验证范围","artifacts":["candidate/app.py","work/report.md"]}
```

evidence authority为observed/static/inferred/designed/native-rea-bundle。resolve仅接受新鲜observed/static/native-rea-bundle；解决时绑定证据完整快照，重登记后需重新核对并resolve。coverage的source为original或supplement:1、supplement:2等，所有来源与所有feature均需映射。覆盖描述由宿主对照用户要求审查，工具不自动理解或发现漏项。deliver拒绝未审覆盖、未解决unknown、失败/失效检查或缺成果。纯分析使用deliver_analysis，无需比较或构建。

进程计划version=2，scope/original/candidate/scenarios/timeout_seconds。两侧argv/cwd/sources；每scenario唯一id和ordered steps；每step含stdin/args/files/expected_exit_codes（原版允许退出码）。cwd和sources是成果相对路径。每scenario分别复制两侧有限源码树，步间保留独立状态；比较stdout/stderr/exit和声明文件字节摘要。文件数量/大小、时间/内存/输出有限制，拒绝链接，清理子进程。例子见tests_next/test_workflow.py和evidence/next/s1/vertical.json。

最小可运行计划如下，将两侧不同实现分别保存在original/app.py与candidate/app.py，argv中的Python路径替换为实际绝对路径：

```json
{
  "version": 2,
  "scope": "实际声明的输入、输出和状态",
  "original": {"argv": ["C:/Python/python.exe", "app.py"], "cwd": "original", "sources": ["original/app.py"]},
  "candidate": {"argv": ["C:/Python/python.exe", "app.py"], "cwd": "candidate", "sources": ["candidate/app.py"]},
  "scenarios": [{"id": "get", "steps": [{"stdin": "{\"op\":\"get\"}", "args": [], "files": ["state.json"], "expected_exit_codes": [0]}]}],
  "timeout_seconds": 3
}
```

argv必须实际调用该侧声明的源码/二进制，外部解释器可用但会绑定路径和摘要。
不能把两侧都指向同一个外部脚本，也不允许inline -c/-e替代声明源码。
外部输入先复制进各自有限目录。比较还绑定全部继承启动环境的合并摘要，不保存环境值。
进程观察不是完整依赖闭包：系统DLL、网络服务或未声明外部状态仍需宿主确认并重新比较。

网页计划version=1,kind=web，scope,original/candidate(url/cwd/sources),scenarios(id/steps),widths,observe,storage_keys,pixel_tolerance。操作click/fill/press/reload/wait/observe。冻结选择器/存储键/容差；实际新context不读用户profile，分别报告DOM/输入/ARIA/指定存储和截图。例子evidence/next/s3/web/plan.json。需受控服务或独立验证URL对应源码；声明文件本身不认证远程实际代码。

结果由实际compare生产，不能record pass。每轮新目录，原始差异保留。缺失观察、同样崩溃、同样缺文件不通过，同源两侧拒绝。结果绑定计划/源码/比较器/证据/功能依据，相关修改失效。复用前检查原回执摘要；改写报告不能制造通过。复用时返回原回执实际路径。默认每check12次，不变通过复用，不变失败/unknown需retry_reason或新内容，预算修改要理由。

回执标rea_native_proof=not-performed，官方有限声明须执行相应REA接口并保留bundle。不是操作系统隔离环境，运行未知软件应符合授权和环境。有限文件/像素对照不保证未列功能或隐藏服务行为。
