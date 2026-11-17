# 可选比较与明确标注的结果审查

本页定义可选工具接口，不规定智能体的工作顺序，也不要求所有成果经过本比较器。已有宿主工具与可靠任务记录可直接沿用；readiness只描述本账本的验收缺口，不限制调查/编辑。自动检查、外部宿主审查和实际交付分别记录；完整接口补充见末尾“自主工作与外部结果审查”。

CLI：open --project-root <absolute> --request <plain words>；status；record --change-file <JSON> --revision <current>；compare --project-root <absolute> --check-id C1 --plan plan.json --output work/round-1。MCP有等价操作，rf_next_case_record公布各操作完整schema。下列格式由智能体生成，零基础用户无需填写。

## 精简入口：要求直接引用真实检查

长复刻默认用一条requirement同时保存需求和功能，不再重复登记技术evidence及coverage。source引用original或supplement:N；宿主review核对原话、检查范围和遗漏，工具不自动发现未声明要求。所有原话来源都有映射才可完整交付；混用旧feature时仍用显式coverage。

```json
{"op":"requirement","id":"R1","description":"保存计数并处理错误输入","source":"original","checks":["C1"],"dimensions":["process:bounded"],"review":"独立原版观察涵盖add/get、持久化及错误退出；其余要求继续保留"}
```

process:bounded仅指有界进程输出/退出/文件；web:declared-behavior和web:pixels分别标识网页已声明行为和像素；REA使用behavioral:维度或structural-function:维度、structural-artifact:overall。结构通过不满足行为维度。status给出verified_dimensions/missing_dimensions；已观察证据、product_identity、验证、交付和剩余项分别返回。

部分阶段可用deliver_stage，明确features及实际产物；其余原话/补充/unknown保留，whole_product_acceptance仍not-established。完整deliver继续要求所有已声明要求通过、全部来源覆盖、未知已解决及当前受检候选身份：

```json
{"op":"deliver_stage","features":["R1"],"summary":"仅计数阶段，网络部分仍未完成","artifacts":["candidate/app.py"]}
```

## 兼容原有记录

旧feature/evidence/coverage操作继续按原义读取，不将历史pass升级为官方证明。record的change使用以下结构（每次使用status返回的最新revision）：

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

新evidence默认retention=snapshot，将最多64MiB观察材料复制到case/evidence/内容摘要文件，保留source_path。
工作文件后来被覆盖不改变历史事实；快照被篡改仍失效。活的规格/源码依赖显式加retention=live；
旧case条目继续按原路径核对，不自动改写或把失效洗成通过。源码、二进制和运行环境的比较身份仍单独核对。
status默认不回传coverage/delivery/unknown中的大输入快照；诊断列出需审条目。case-v2.json保留当前状态和引用，事件及超过64KiB的文本按摘要保存在同case的case-records中，读取时验证并还原；搬家须复制整个case目录。单个主记录／事件限16MiB，大文本限64MiB，写入超限在替换旧记录前失败。

复刻交付前必须登记产品身份；deliver要求全部候选身份文件列入交付、身份当前。每条交付功能（及其必要依赖）的有效检查都须覆盖所声明的产品文件；只从同一份回执确实配对当前候选与参照身份的检查累计覆盖，不从别的功能或不相干两侧拼接产品证明。deliver_stage只检查所选功能及其必要依赖，无关损坏回执保留局部缺口：

```json
{"op":"product","candidate_files":["candidate/main.py"],"reference_files":["original/product.exe"],"review":"候选入口和原版可执行文件分别标识交付对象；共享素材不作为身份"}
```

这只核对声明的产品文件。更新后实际启动哪个程序、运行时模块与功能仍要独立验证，不能把原版安装启动当作候选升级成功。

耗时验证/打包可用同一record入口执行已有项目脚本，宿主普通工具仍保留：

```json
{"op":"execute","id":"verify-export","kind":"verify","features":["F-export"],"argv":["C:/Python/python.exe","tools/check_export.py"],"cwd":".","inputs":["tools/check_export.py","candidate/export.py"],"artifacts":["work/export-observation.json"],"purpose":"验证本次导出变化的文件和错误分支","timeout_seconds":60,"reusable":true}
```

kind为investigate/verify/visual/package；argv不经shell拼接，代码保存在声明的项目文件，输入列明实际相关代码/配置。
保存日志、退出、耗时、清理及产物摘要；进程超时/取消/缺产物/输入执行中改变保留unknown。
reusable仅用于明确无未绑定外部状态的verify/package操作；输入、实际运行器、声明环境和产物均不变才复用。
同输入失败需retry_reason或改输入；默认连续三次相同失败后回调查，不可只改ID绕过。成功的非复用观察可正常重复。确有新依据时用budget的max_operation_failures（1–100）与reason调整失败预算。
这不是依赖自动发现：外部模块、服务、设备或GUI状态变化要作为新输入，或reusable=false。
execute绝不写入检查pass；外部脚本报告仍为观察依据，真正验收调用独立compare。
验证按改动选：后端先接口/源码回放，UI变化再查受影响页面/完整滚动和交互，阶段集成或打包变化再整包。

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

argv必须实际调用该侧声明的源码/二进制，执行使用已摘要的绝对路径；侧目录内程序映射到该侧执行副本。外部Python/Node解释器只支持可识别的脚本入口和有限无歧义选项，拒绝help/version/eval/module等提前结束或改变入口的选项；其他外部启动器保留为未适配，而非仅凭argv中有文件名授予比较资格。宿主Python的精确字节副本也可识别，改名不放松实际内容绑定。
不能把两侧都指向同一个外部脚本，也不允许inline -c/-e替代声明源码。
外部输入先复制进各自有限目录。进程使用明确的系统/解释器环境，应用额外需要的环境键
在计划顶层environment_keys数组中声明；其它宿主内部变量不传入目标。
比较绑定实际传入环境的合并摘要，不保存环境值，CLI与MCP可共享同一结果。
进程观察不是完整依赖闭包：系统DLL、网络服务或未声明外部状态仍需宿主确认并重新比较。

网页计划version=1,kind=web，scope,original/candidate(url/cwd/sources),scenarios(id/steps),widths,observe,storage_keys,pixel_tolerance。操作click/fill/press/select/check/dialog/storage/reload/wait/observe/scroll。冻结选择器/存储键/容差；实际新context不读用户profile，分别报告DOM/输入/ARIA/原生校验/对话框/指定存储和截图。例子evidence/next/s3/web/plan.json。需受控服务或独立验证URL对应源码；声明文件本身不认证远程实际代码。

select使用selector/value；check使用selector/checked布尔值；dialog用decision=accept或dismiss及value字符串，
在触发确认/提示框的click之前声明，实际比较类型、文字及处理结果；未声明的对话框导致unknown，不能静默取消后算通过。
每步默认整页截图（单图上限1600万像素，超出保留unknown），而非只截800px首屏。懒加载或嵌套滚动需显式scroll及后续wait／observe场景，例如{"action":"scroll","selector":"#footer"}。采集JSON与全部截图摘要绑定回执，缺失或改变使旧检查失效。

storage使用key/value字符串且key必须列入storage_keys，可准备损坏/边界状态后reload。例子：

```json
{"action":"select","selector":"#order","value":"name"}
{"action":"check","selector":"#enabled","checked":true}
{"action":"dialog","decision":"accept","value":""}
{"action":"click","selector":"#clear"}
{"action":"storage","key":"state","value":"invalid-json"}
{"action":"reload"}
```

结果由实际compare生产，不能record pass。每轮新目录，原始差异保留。缺失观察、同样崩溃、同样缺文件不通过，同源两侧拒绝。结果绑定计划/源码/比较器/证据/功能依据，相关修改失效。复用前检查原回执摘要；改写报告不能制造通过。复用时返回原回执实际路径。默认每check12次，不变通过复用，不变失败/unknown需retry_reason或新内容，预算修改要理由。

回执标rea_native_proof=not-performed，官方有限声明须执行相应REA接口并保留bundle。不是操作系统隔离环境，运行未知软件应符合授权和环境。有限文件/像素对照不保证未列功能或隐藏服务行为。

## 原生REA验证计划（kind=rea）

通过同一个rf_next_compare入口实际启动固定REA stdio、import原bundle、调用公开verify_reconstruction、export原结果。未改写官方schema或Evidence；自有comparison.json仅索引原结果。先用原工具采集/比较并export到成果项目，再生成计划：

```json
{
  "version": 2, "kind": "rea", "scope": "仅声明的原生主张",
  "bundle": "work/original-bundle.json", "timeout_seconds": 60,
  "original": {"cwd": "original", "sources": ["original/product.exe"]},
  "candidate": {"cwd": "candidate", "sources": ["candidate/product.exe"]},
  "specification": {"name": "已审查的主张", "claims": [
    {"claim_id": "Structure", "title": "结构范围", "comparison_evidence_id": "ev_[实际64位摘要]",
     "kind": "structural-artifact", "dimension": "overall"}
  ]}
}
```

specification完全使用实际公开合同；参考在left、候选在right。适配器核对每个主张所选source Evidence的subject.local_path与sha256，须精确覆盖声明sources，且都是当前对应侧文件。无关bundle中的pass、缺source、错候选、篡改bundle、原生unknown均不转成合格检查。纯验证不启动反编译provider。

保存native-response.json和native-bundle.json原结果，comparison.json标owned-result-index，rea_native_proof只给原bundle/operation/evidence_id引用。原生未知ID来自原结果，不能用本地resolve关闭；更新原bundle后重新验证。状态pass仅对应明确主张，结构、函数和行为范围不互相升级。

新鲜性绑定原bundle/计划、选定subject内容、Node/官方JS代码、传输实现、适配器和相关环境摘要，以及保留的原响应/bundle。只验证被声明的文件，不推断未声明的DLL、远程服务或设备状态。文件摘要也不是来源真实性或当前服务状态证明。原生coverage/obligation及设备/项目专用测试尚未适配为本地检查，继续用其真实结果独立报告；不接收手填pass或自造官方proof。

搬家保留原bundle与ID不改写，旧检查失效；原subject路径不会被悄悄重绑定到新候选。重新观察/导入真实新位置材料并比较。

## 静态复核后的兼容及边界补充

本节随2026-11-18静态复核修复更新；本轮未执行功能测试或启动provider/目标，旧179项通过只对应修复前源码。

- 同ID的requirement/feature更新保留既有来源、维度与非该接口负责的约束；requirement继续保留既有evidence/dependencies，旧feature继续保留requirement_source/dimensions。requirement更新不接受隐式减少维度或更换原话来源，实质范围变化另记新要求/补充。
- 比较结果接纳核本次run_id和受影响功能输入、就绪状态及通过结果的新鲜性，无关功能/预算更新不撤销独立运行。实际输入变动仍使结果失效；失败、unknown和中断不伪装通过。
- 进程stdout/stderr保存到输出目录channels下的内容寻址文件，回执仅放bytes/sha256/snapshot；fresh核文件存在、长度和摘要。每次进程原输出预算不变，整轮通道输出额外限64MiB（按观察累计，单步越界保留unknown）；旧内联base64回执仍可读取，但引擎身份变化后不会自动变成当前通过。
- 网页检查在执行前后及复用时绑定当前选择的浏览器、Node、实际Playwright代码和相关环境摘要。旧回执缺web_runtime则失效，须有据重验。
- 原生行为捕获与结构观察采用不同绑定：结构读取artifact subject；行为读取官方capture manifest的绝对executable、selected/actual executable SHA、身份状态及场景/比较合同承诺（其内容合法性由原生导入/验证检查）。当前只接入每侧一个可认证的直接可执行文件；解释器脚本/模块、附属输入文件和其他未被capture承诺的依赖不凭路径或当前摘要升级为历史证据，保留unknown。该限制也不替代共享库、远程服务或设备状态观察。
- refine_route保存技术hint用于恢复method_reads，原始用户目标不变。旧已细化方法提示保留，短required_reads仍采用当前合同。

## 自主工作与外部结果审查

这些是可选记录接口，不是操作顺序。未使用case也可通过可靠宿主记录保留目标和成果；本页仅说明选择该账本时如何避免虚假完成。当前改动按用户要求仅静态校验，新增用例未执行。

### 可选记忆

MCP rf_next_case_open新增recording=auto/case/skip，CLI open对应--recording。auto保留旧意图分类行为；case明确保存当前目标（包括普通开发）；skip直接返回host-native且不创建账本。方法资源缺失只作为route.advisory-unavailable提示，不阻断保存原话或宿主工作。

```json
{"op":"checkpoint","note":"当前进展、已知事实和阻碍","next_action":"宿主自行选择的下一步","paths":["work/observation.txt"]}
```

checkpoint不要求features/checks，不产生通过或完成。status.workflow_policy明确host_work_allowed=true；ready/blocked只是本账本的验收诊断。宿主仍可直接调用分析、调试、设备、构建和编辑工具，不要求把这些操作先变成脚本或登记execute。

### 外部观察的显式宿主审查

对设备、第三方工具、项目脚本或其他尚未接入内部检查器的结果，先保留实际观察，再可选登记：

```json
{"op":"requirement","id":"R1","description":"已声明的设备行为","source":"original","checks":[],"dimensions":["device:behavior"],"review":"核对用户原话、场景与局限","evaluation":"host-review"}
```

```json
{
  "op":"assessment","id":"A1","features":["R1"],
  "observations":["work/raw-device-observation.txt"],
  "candidate_files":["candidate/app.apk"],"reference_files":["original/app.apk"],
  "input_paths":["work/scenario.txt"],"dimensions":["device:behavior"],
  "producer":"实际工具及版本","operation":"实际执行的操作",
  "context":"设备/环境/账号状态/观察时间等必要条件，不含凭据",
  "scope":"这份结果实际覆盖什么，不覆盖什么",
  "basis":"original-comparison","outcome":"pass",
  "review":"宿主核对原始观察、候选身份、行为范围和异常分支的具体依据",
  "limitations":["有限观察，未覆盖的服务/设备状态保留"],"valid_for_seconds":3600
}
```

- 这不是导入某个任意JSON里的pass：适配器不认证任意专业格式，也不执行该外部工具。它保存独立标注的host-reviewed判断和原观察副本，**从不写case.checks或官方REA Evidence**。不得把模型生成的报告当成工具确实执行的证明。
- basis为original-comparison/specification/observation，outcome为pass/fail/unknown。原版对照需要独立两侧身份；规格检查需要候选和当前规格/input_paths；普通观察可不声明候选，但不能凭它交付一个未绑定的程序。
- observations为1..50个已存文件，每个最多64MiB；冻结快照。candidate/reference/input文件摘要保持当前，绑定受影响要求、来源/上下文、维度与限制，valid_for_seconds为1..86400秒。
- 时间窗只是审查适用期，不证明设备/服务没变化。新外部状态要重新取证/审查；缺失、过期、输入变化或观察篡改使审查失效。fail/unknown不会因过期自动消失，需新依据更新同一assessment。
- requirement.evaluation默认automatic，旧接口不变。显式host-review允许checks为空和自定义命名维度（如device:behavior），但仍需当前有据审查；若声明了内部checks，它们也要通过。新旧登记接口保留原维度和依赖。
- status分别给complete/verified（内部自动检查）、host_reviewed、accepted、external_review和缺口。accepted不改写complete；剩余自动验证另列remaining_automatic_verification。相关依赖未accepted会继续影响使用它的要求。阶段审查不扩散无关失败。

### 交付类型不能悄悄替换

```json
{"op":"output_goal","kinds":["independent-reimplementation","modified-original"],"source":"supplement:1","review":"用户在该条补充中明确接受两种成果；不是工具自动授予授权"}
```

类型：analysis-report、independent-reimplementation、specification-implementation、modified-original。这是宿主对原话/补充的明确映射，工具不能证明用户语义；新补充使旧映射待复核。未登记时按旧目标保守默认分析报告或独立重写，不默认允许改原程序。技术换路无需改目标，实质输出取舍须以已取得的用户决定为依据。

product可加kind；默认independent-reimplementation。规格实现可reference_files=[]，其余保留独立原版/候选。按规格单测只证明规格范围，不叫原版等价；原程序改版也不叫独立源码。旧deliver/deliver_stage保持自动门，不被assessment写成pass。

```json
{"op":"deliver_reviewed","kind":"independent-reimplementation","scope":"stage","features":["R1"],"summary":"明确宿主审查范围、成果和剩余项","artifacts":["candidate/app.apk"]}
```

独立宿主审查路径：scope为full/stage。核当前allowed output kind、全部交付文件、所选要求及依赖、当前原观察和产品身份、相关未知；完整交付还须原话/每条补充覆盖。每条要求的证据必须对应所交付的当前候选；独立重写/修改原程序要求原版对照依据，规格实现要求规格依据。原生unknown不能在本地抹去，宿主审查也不能伪称官方已解决。

结果是host-reviewed-delivery或host-reviewed-stage-delivery，不是自动pass。自动检查与外部审查可以共同支撑范围，但不可相互冒充。scope=stage保留原目标、剩余要求与局限。新补充、产品变化、受影响输入/审查变更或过期使相应交付失效；搬家保留历史观察但失效外部审查与交付。
