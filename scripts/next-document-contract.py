"""Apply the explicitly selected v2 public document/skill contract in this checkout."""
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
DOCS={
'RULES.md':'''# Reverse + enhanced REA contract

Runtime: preserved Reverse domain methods + official REA 6.9.0 with explicitly owned enhancements. Current host reasons and writes. Craft has zero runtime dependency. Spec is optional, never an installation/readiness prerequisite.

Start with the original plain request using rf_next_case_open (or python -m rea_enhanced open). Ordinary development remains host-native. Continue the existing case; record supplements, not a new objective. Read the returned domain skill, required_read_paths and pinned official REA skill before specialist operations. Domain installation hints do not override this contract.

One outcome case owns the goal, features, dependencies, evidence pointers, unknowns and checks. Official REA evidence stays in original bundles; export into the case and import on restart. Host-supplied provenance is labeled. Do not fabricate native proof or treat route pass as analysis success.

Investigate identity and static evidence when informative. Select observation, providers, unpacking or other methods from actual findings and the authorized task. A key/account is a condition to record, not a universal bypass/dump workflow. Memory capture does not automatically avoid protections or recover source. Missing dependencies block affected functions. Ask concrete human questions only when necessary; continue independent work.

Before implementation record behavior evidence, dependencies, semantic review and checks. Retain all original requirements; an initial slice does not reduce the final goal. Current host implements/builds in the outcome project without a second model. Raw analysis may continue when a provider is missing, keeping dependent official claims unverified.

Actual independent replay compares declared behavior/state/files; web replay separates DOM/storage behavior from pixels. Freeze reference exits and visual tolerance first. Missing observations, crashes and interrupted work cannot pass. Related changes invalidate old success. Reuse unchanged passes; failed unchanged attempts need new information. Respect budgets, preserve failures and clean owned descendants. The tools are not an OS sandbox.

Report analysis, feature checks, full-goal coverage and deployment separately. finite-scope-verified is not automatic whole-product acceptance; the host must review omitted requirements. Source recovery, equivalent source and modified binaries are distinct deliveries.

Installation: docs/AGENT-BOOTSTRAP.md is the only public entry. Only owned skill/AGENTS/MCP regions may be changed. Preserve unrelated configuration and credentials. Legacy v1 installers/checkpoints/source are historical. docs/ACTIVE-DOCUMENTS.json lists current public documentation; development resumes from docs/NEXT/RESUME.md and STATUS.json.
''',
'docs/AGENT-WORKFLOW.md':'''# 白话任务如何运行

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
''',
'docs/AGENT-BOOTSTRAP.md':'''# 唯一安装入口：Windows x64 / Codex

先读CURRENT-STATE.md确认本版资格。完整核心为Reverse方法、固定Node、官方REA、独立Frida绑定和增强入口。没有Craft，不强制Spec，不启另一个模型或账号。

把本版放长期保留的独立目录；Python 3.11+，执行：

```powershell
powershell -NoProfile -File .\\scripts\\install.ps1
```

安装器创建仓库.venv和固定Python依赖，按摘要从固定来源取得Node/REA/Frida/WABT/JADX；npm按锁文件下载且不运行生命周期脚本。随后保存本机工具路径。Ghidra/Java、浏览器、设备、ILSpy和其他provider按目标需要，路径存在不等于实际操作通过；缺少工具不会冒称该类目标可验收。

默认只管理当前Codex的reverse-fusion用户技能、全局AGENTS托管段、一个reverse-fusion-rea MCP。保留无关配置与凭据。已有另一checkout的托管入口时显式指定旧绝对路径：

```powershell
.\\scripts\\install.ps1 -ReplaceFrom 'D:\\Project\\reverse'
```

安装实际连接登记命令并运行目标无关操作，失败恢复旧段。输出rollback_receipt仅含托管段，保存在state/migrations。回退：仓库Python -m rea_enhanced rollback --receipt '<回执绝对路径>'。

隔离安装用-HomeDirectory '<临时目录>'；只准备运行包用-PrepareOnly。检查入口：仓库Python -m rea_enhanced mcp-check。同名非托管条目或被改过的托管内容拒绝覆盖。安装回执不等于软件复刻验收。

完成后重连工具或新建聊天；旧桌面连接不一定自动切换。其他宿主可适配相同stdio和指引，但本安装器只管理Codex；未知宿主需核对实际接口。历史四组件安装脚本不可运行。
''',
'docs/DEPLOYMENT-GUIDE.md':'''# 部署

唯一流程见[AGENT-BOOTSTRAP](AGENT-BOOTSTRAP.md)。本版Windows x64核心是Reverse＋增强REA，不走旧四组件安装链。

共享目录长期存在。用户在任意成果目录打开Codex，用白话提出任务。用户级技能/全局指引负责发现，共享目录提供方法工具，成果留在用户项目。空文件夹也能调用；移动共享目录后重新部署绝对入口。

provider路径保存在state/rea-providers.json，只含路径。更换后providers --refresh、mcp-check，并实际执行所需操作。原REA包不改，Frida绑定独立安装；增强比较回执单独标识。
''',
'docs/CODEX-INTEGRATION.md':'''# Codex接入

托管用户技能、全局AGENTS段和一个reverse-fusion-rea MCP：共享仓库Python -m rea_enhanced mcp，cwd为checkout。包含原REA工具与四个rf_next_*工具。当前宿主唯一推理/编码，无Craft后台。

在任意成果项目用白话对话，入口提示保留目标和调用方法。mcp-check证明实际登记命令可连，不证明旧聊天热更新。重连/新聊天以客户端加载结果为准。流程见AGENT-WORKFLOW，安装见AGENT-BOOTSTRAP。
''',
'docs/BEGINNER-GUIDE.md':'''# 零基础使用

安装一次后，在要开发的软件文件夹打开智能体，用自己的话描述。共享工具目录要保留，不用复制技能，不用记工具名。

- “帮我分析这里的软件，再做出功能和使用效果一样的版本。我不懂技术，需要我操作时请说清楚。”
- “这是我自己的APK，先帮我看懂怎么工作，目前只要分析报告。”
- “照这个网站做一个，外观和交互都要核对。缺后台资料请具体告诉我。”
- “帮我开发库存管理软件。”普通开发走正常流程，需要调查再调用领域工具。

有合法可用账号/卡密时说“我能正常进入，可以配合操作”；没有时说“目前进不去”。秘密不要写进报告。智能体先调查材料，再说明具体需要什么，不要求你选择调试/dump等专业方法。

补充说“刚才要求保留，再增加……”。中断说“继续上次”，应恢复同case；多个案例不明确才问是哪一个。可问“最开始的要求，还有哪些没做完？哪些实际比较过？”。

分析结束不代表复刻完成，外观相似不表示业务一致。不可观察的服务端行为列缺口，继续独立部分。换电脑让智能体按AGENT-BOOTSTRAP.md安装，核真实连接，再在成果项目对话。
''',
'docs/RECOVERY.md':'''# 恢复

开发从NEXT/RESUME.md和STATUS.json恢复，按唯一next_action。旧RF检查点是历史，不重启旧任务。

成果先status读取case-v2.json的原话、补充、证据、unknown、检查和下一步。index只发现case，不是第二权威。重启import原REA bundle；不覆盖旧记录。v1 case默认只读，选择新case明确导入有依据材料。

中断不算通过，保留原输出，用新目录再比较。检查文件锁防并发、expected_revision防旧状态覆盖。相关变化使旧结果失效；不变失败需新信息，预算耗尽回分析或记理由调整。

工具失败先记实际错误、确认自有进程清理再换方法。路径失效providers --refresh和mcp-check后实测需要的操作。缺工具仅阻断相关功能。

安装失败恢复托管段；异常中断可用prepared回执rollback。托管内容已改时拒绝覆盖，留待检查。回退保留新加的无关配置。旧checkout和基线标签保留，不删仍被其他聊天使用的目录。回退后重连。
''',
'docs/NATIVE-COMPONENTS.md':'''# 当前真实组件

Reverse：固定领域正文、单一路由、困难方法按需读。

官方REA 6.9.0：原工具schema/结果/错误/bundle保持原身份。增强REA单stdio入口保留原工具并添加四个工具。Node 24.22.1、独立Frida 17.23.2绑定固定；实际provider资格靠真实操作，不靠目录存在。

增强部分：宿主原生实现、功能依据/依赖、独立进程/文件/状态和网页行为/视觉比较、新鲜度、预算与恢复。其回执不是REA官方proof。详见COMPARISON及INTEGRATION-CONTRACT。

Craft源码/二进制/服务不需要，Spec可选。旧源码、文档和测试仅追溯，不驱动安装。媒体资产用宿主现有媒体能力，不能伪称旧Craft服务已运行。
''',
'docs/MCP-INTEGRATION.md':'''# 一个增强REA连接

名称reverse-fusion-rea，命令为本仓库.venv Python -m rea_enhanced mcp，cwd为checkout。保留原REA工具/prompts，新增rf_next_case_open、rf_next_case_status、rf_next_case_record、rf_next_compare。

mcp-check实际初始化、分页目录、binary_session、Frida枚举与进程清理。登记不证明旧桌面聊天热更新，需实际重连。宿主仍唯一推理与编码。

providers --refresh保存路径，CLI/MCP共用；路径不证明目标工具操作成功。原REA证据导出到成果case，重启原样导入。按目标接其他工具，不把全部provider强制开机。
''',
'docs/INTEGRATION-CONTRACT.md':'''# 职责与边界

Reverse负责领域方法/路由；官方REA负责原工具与证据；增强层负责目标/依据/依赖/有限比较/失效/恢复；当前宿主负责理解、语义审查、提问、实现及全目标核对。

没有Craft后台、强制Spec或第二模型。参考Craft有界构建/比较/修正思路后独立实现，没有隐藏运行依赖。来源见SOURCE-MANIFEST。

机器检查已声明的摘要和依赖，不能证明宿主没有遗漏要求，也不能阻止宿主直接编辑。有限比较不认证远程网站源码映射或隐藏服务端行为。已列检查通过不能推导任意软件、壳、卡密或反调试均可解决。
''',
'docs/CROSS-PROJECT-WORKFLOW.md':'''# 跨项目

共享checkout仅工具/技能，project_root始终是当前成果项目绝对路径。open恢复同case，读返回领域与官方方法。case-v2、原bundle、比较输出都在成果目录。CLI默认当前目录，不为方便切到工具库写成果。

空目录仍由全局入口找到共享工具。v1 case不隐式升级；明确选择新case引入原材料。普通开发不建case，需要调查可在项目中按需建立。见AGENT-WORKFLOW。
''',
'docs/HOST-PROJECT-CONNECTION.md':'''# 宿主与项目

当前自动部署范围Windows x64 Codex。其他宿主可适配共同stdio/领域方法；同样有AGENTS或技能不证明实际接口完全相同。本版不自动部署到Pi/Claude，也不要求第二宿主模型登录。旧宿主记录属于v1历史。

入口指向长期保留的共享checkout，成果随当前项目；见CODEX-INTEGRATION和AGENT-WORKFLOW。
''',
'docs/COMPARISON.md':'''# 有限比较

CLI：open --project-root <absolute> --request <plain words>；status；record --change-file <JSON> --revision <current>；compare --project-root <absolute> --check-id C1 --plan plan.json --output work/round-1。MCP有等价操作。record支持supplement/evidence/feature/unknown/resolve/refine_route/deliver_analysis/budget；可运行格式见tests_next/test_workflow.py。

进程计划version=2，scope/original/candidate/scenarios/timeout_seconds。两侧argv/cwd/sources；每scenario唯一id和ordered steps；每step含stdin/args/files/expected_exit_codes（原版允许退出码）。cwd和sources是成果相对路径。每scenario分别复制两侧有限源码树，步间保留独立状态；比较stdout/stderr/exit和声明文件字节摘要。文件数量/大小、时间/内存/输出有限制，拒绝链接，清理子进程。例子见tests_next/test_workflow.py和evidence/next/s1/vertical.json。

网页计划version=1,kind=web，scope,original/candidate(url/cwd/sources),scenarios(id/steps),widths,observe,storage_keys,pixel_tolerance。操作click/fill/press/reload/wait/observe。冻结选择器/存储键/容差；实际新context不读用户profile，分别报告DOM/输入/ARIA/指定存储和截图。例子evidence/next/s3/web/plan.json。需受控服务或独立验证URL对应源码；声明文件本身不认证远程实际代码。

结果由实际compare生产，不能record pass。每轮新目录，原始差异保留。缺失观察、同样崩溃、同样缺文件不通过，同源两侧拒绝。结果绑定计划/源码/比较器/证据/功能依据，相关修改失效。默认每check12次，不变通过复用，不变失败/unknown需retry_reason或新内容，预算修改要理由。

回执标rea_native_proof=not-performed，官方有限声明须执行相应REA接口并保留bundle。不是操作系统隔离环境，运行未知软件应符合授权和环境。有限文件/像素对照不保证未列功能或隐藏服务行为。
'''
}


def main():
    if (ROOT/'docs/ACTIVE-DOCUMENTS.json').exists():
        raise SystemExit('One-time S4 contract migration already applied; maintain current documents directly.')
    for name,text in DOCS.items(): (ROOT/name).write_text(text,encoding='utf-8',newline='\n')
    reconstruction='''---
name: reconstruction
description: 有依据的独立复刻、原版比较与追版；当前宿主实现，原REA证据及增强检查，无强制Spec/Craft。
---

# 有依据的复刻与追版

根RULES和docs/AGENT-WORKFLOW是当前合同。保存原话、恢复case-v2，不建第二权威。泛化复刻先分析，实际领域明确后同case refine_route。路由通过不是分析成功。

读取../field-journal/_index.md及相关先例，只作方法参考。核目标身份、授权、输入/输出/状态/错误/副作用及外部依赖。读固定REA包官方技能和相关方法，调用现有实际provider，不手写替代反编译器。

每待实现功能record feature，含description/evidence/checks/dependencies/review，保留全部原目标待办。推断/设计与观察/静态事实分开。critical unknown仅阻断相关功能。可先做可验证切片，不改最终范围。纯分析deliver_analysis无需构建，已有成果验证不重建规格。

原REA调查结束export_evidence_bundle到成果case，保留原ID/provider/limitations/unknown，重启import原bundle。增强case引用文件，不改原REA账本，不编造官方proof。

当前宿主唯一原生写入/构建/运行者，不另启模型。Craft零运行依赖，Spec可选。旧参考的四组件流程仅历史。按docs/COMPARISON冻结有限两侧计划，独立执行、分别报告行为与视觉；候选单测不能替代对照。覆盖选定正常/边界/错误/状态/副作用，用故意错误候选检验比较器。

失败差异回实现/分析，unknown保留；相关变化使旧通过失效，不修改预期迁就候选。不变通过复用、不变失败需新信息，遵守预算。中断先恢复清理，使用新输出目录。成果不写共享工具库。

追版固定O旧原版/C我方/N新原版及来源；保留原设计与旧记录，只纳入有据新变化，旧地址或相似度不证明语义。

交付区分可读分析、源恢复依据、等价源码或修改二进制、有限比较、构建/运行及剩余目标。finite-scope-verified不自动关闭全目标；回看原话与补充，不降为演示。需要用户操作时解释具体问题，工具选择由宿主负责。
'''
    (ROOT/'skills/reconstruction/SKILL.md').write_text(reconstruction,encoding='utf-8')
    names=['skills/SKILL.md','skills/MASTER-ROUTING.md','skills/ops/IDENTITY.md','skills/ops/role-map.md','skills/ops/guided-operator-contract.md','skills/reverse-engineering/SKILL.md']
    for name in names:
        p=ROOT/name;text=p.read_text(encoding='utf-8').replace('reverse_fusion bridge','rea_enhanced open')
        replacements={'必装REA/官方Spec/nativeCraft':'Reverse方法/增强REA','实际安装REA/官方Spec/nativeCraft':'实际安装Reverse方法/增强REA','复用官方 REA 和 Spec Kit':'复用官方 REA 和增强比较','真实Spec/Craft交接':'当前组件合同','当前宿主推理，真实native Craft负责复刻写入与检查。':'当前宿主原生实现与构建，增强REA独立比较，不运行Craft、不强制Spec。','reconstruction/Spec Kit':'reconstruction with enhanced REA','Spec Kit starts in the independent deliverable project after behavior Evidence handoff.':'Current host implements after evidence review; Spec is optional and Craft is not used.'}
        for a,b in replacements.items():text=text.replace(a,b)
        lines=text.splitlines()
        for i,line in enumerate(lines):
            if line.startswith('- **R46当前实现owner**'):lines[i]='- **当前实现owner**：当前宿主唯一推理和原生写入者，按reconstruction记录依据、依赖和真实独立比较。不启第二模型，不运行Craft、不强制Spec。'
            if line.startswith('| **implementation-worker**'):lines[i]='| **implementation-worker** | 实现职责 | 当前宿主按依据原生实现，独立比较，不另启模型 | reconstruction/ |'
        p.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for name in ['execution-backend.md','evidence-to-spec.md','differential-validation.md','handoff-manifest.md']:
        (ROOT/'skills/reconstruction/references'/name).write_text('# 当前增强REA衔接\n\n当前执行见[复刻技能](../SKILL.md)、共享docs/AGENT-WORKFLOW.md及docs/COMPARISON.md。case-v2保存原话、功能依据、依赖、unknown和检查；当前宿主原生实现，原REA证据原样保存，自有比较明确标识。Craft不运行，Spec不强制。原详细合同从baseline/rf-1.4.0标签追溯，不是当前执行要求。\n',encoding='utf-8')
    for name in ['spec-kit-workflow.md','upstream-follow-update.md']:
        p=ROOT/'skills/reconstruction/references'/name
        text=p.read_text(encoding='utf-8')
        if not text.startswith('> v2适配'):
            p.write_text('> v2适配：本文旧Spec/Craft/旧case格式指令为历史参考，当前case-v2、宿主实现和增强比较遵循上级SKILL及根RULES；Spec仅可选。O/C/N证据审查方法仍适用。\n\n'+text,encoding='utf-8')
    p=ROOT/'components/reverse-core/preservation.json';manifest=json.loads(p.read_text(encoding='utf-8'))
    for name,entry in manifest['files'].items():
        data=(ROOT/name).read_bytes();data=data if name.endswith('.jar') else data.replace(b'\r\n',b'\n')
        new=hashlib.sha256(data).hexdigest()
        if entry['sha256']!=new:
            entry.setdefault('upstream_sha256',entry['sha256']);entry['sha256']=new
            entry['patch_reason']=entry.get('patch_reason','')+'; v2 adaptation: host implementation and enhanced comparison replace mandatory Craft/Spec; domain origin retained'
    p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    active=['README.md','AGENTS.md','RULES.md','SOURCE-MANIFEST.json','release/manifest.json','components/official/manifest.json','docs/CURRENT-STATE.md']+sorted(set(DOCS)-{'RULES.md'})
    (ROOT/'docs/ACTIVE-DOCUMENTS.json').write_text(json.dumps({'version':'2.0.0.dev0','active':active,'continuity':'docs/NEXT/*','domain_methods':'skills/**; root contract supersedes inherited integration instructions','historical':'Other inherited docs, specs, checkpoints, evidence and v1 scripts are history; original contract at baseline/rf-1.4.0'},indent=2)+'\n')
    for name in ['components/official/manifest.json','SOURCE-MANIFEST.json']:
        p=ROOT/name;old=json.loads(p.read_text(encoding='utf-8'));components=[]
        for component in old['components']:
            if component['id'] in {'spec-kit','craft-bounded','craft-mcp'}:continue
            if component['id']=='rea':component['role']='fixed official tools/results/evidence backend wrapped by enhanced endpoint'
            components.append(component)
        components.append({'id':'rea-enhanced','kind':'owned-enhancement','path':'rea_enhanced','role':'host-driven case, evidence readiness, independent finite comparison and recovery','craft_runtime':False,'spec_mandatory':False,'design_reference':'https://github.com/storytold/craft-anything; independent implementation, no source/runtime dependency'})
        p.write_text(json.dumps({'schema_version':2,'version':'2.0.0.dev0','project':'reverse-rea-next','components':components,'historical_baseline':'baseline/rf-1.4.0','core_pins':['vendor/rea/manifest.json','vendor/node/manifest.json','components/rea-enhanced/provider-bindings.json']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'release/manifest.json').write_text(json.dumps({'schema_version':2,'version':'2.0.0.dev0','edition':'windows-x64-codex','status':'qualification-in-progress','requirements':'docs/NEXT/REQUIREMENTS.md','current_status':'docs/NEXT/STATUS.json','craft_runtime':False,'spec_mandatory':False,'test_suite':'tests_next','baseline':'baseline/rf-1.4.0'},indent=2)+'\n')
    print(json.dumps({'active_docs':len(active),'preserved_files':len(manifest['files'])}))


if __name__=='__main__':main()
