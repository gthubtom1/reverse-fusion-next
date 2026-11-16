# 有限比较

CLI：open --project-root <absolute> --request <plain words>；status；record --change-file <JSON> --revision <current>；compare --project-root <absolute> --check-id C1 --plan plan.json --output work/round-1。MCP有等价操作。record支持supplement/evidence/feature/unknown/resolve/refine_route/deliver_analysis/budget；可运行格式见tests_next/test_workflow.py。

进程计划version=2，scope/original/candidate/scenarios/timeout_seconds。两侧argv/cwd/sources；每scenario唯一id和ordered steps；每step含stdin/args/files/expected_exit_codes（原版允许退出码）。cwd和sources是成果相对路径。每scenario分别复制两侧有限源码树，步间保留独立状态；比较stdout/stderr/exit和声明文件字节摘要。文件数量/大小、时间/内存/输出有限制，拒绝链接，清理子进程。例子见tests_next/test_workflow.py和evidence/next/s1/vertical.json。

网页计划version=1,kind=web，scope,original/candidate(url/cwd/sources),scenarios(id/steps),widths,observe,storage_keys,pixel_tolerance。操作click/fill/press/reload/wait/observe。冻结选择器/存储键/容差；实际新context不读用户profile，分别报告DOM/输入/ARIA/指定存储和截图。例子evidence/next/s3/web/plan.json。需受控服务或独立验证URL对应源码；声明文件本身不认证远程实际代码。

结果由实际compare生产，不能record pass。每轮新目录，原始差异保留。缺失观察、同样崩溃、同样缺文件不通过，同源两侧拒绝。结果绑定计划/源码/比较器/证据/功能依据，相关修改失效。默认每check12次，不变通过复用，不变失败/unknown需retry_reason或新内容，预算修改要理由。

回执标rea_native_proof=not-performed，官方有限声明须执行相应REA接口并保留bundle。不是操作系统隔离环境，运行未知软件应符合授权和环境。有限文件/像素对照不保证未列功能或隐藏服务行为。
