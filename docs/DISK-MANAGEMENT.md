# 临时文件与磁盘空间

2.3.0 增加真实磁盘生命周期。旧版只管理进程清理，比较副本和宿主自行创建的工作目录
会持续积累。新机制管理明确登记的临时空间，保护分析证据和成果。

默认策略：每个项目临时预算 4 GiB；每个磁盘保留至少 2 GiB 或总容量的 2%，取较大者。
同一用户运行的多个 Codex/MCP/CLI 项目共用按卷加锁的预留登记，新任务同时扣除其他项目的
预留后再判断余量。不同磁盘独立协调。预留是保守的并发协调，磁盘监测是软限制，
不是操作系统配额；任意外部程序或未登记写入仍会占用磁盘。

增强比较逐场景创建执行副本，观察结束即回收，不累计所有场景的副本。
退出码、标准输出/错误、比较结果继续保存；声明观察的文件以内容摘要去重保存到
比较目录 effects，必要的网页截图、原生 REA bundle、源码、样本和交付文件继续保留。
原生回放两侧各有独立的 TEMP/TMP/TMPDIR，也随场景结束回收，避免污染系统临时目录。
这些必要证据仍会增长，应按实际验证需要选择观察范围，而不是每次编辑都重跑全部。

可选 record execute 为每次脚本创建临时目录，将 TEMP/TMP/TMPDIR 和 RF_NEXT_SCRATCH
指向它，结束后回收。脚本需要主动使用这些位置；artifacts 声明只标识成果，不改写
脚本硬编码的输出路径。默认单次脚本临时预算 256 MiB；明确需要时传 scratch_bytes。
正在运行的自有操作持有 OS 租约，定时清理读到活跃租约就保留，避免 PID 重用误判。
每约 0.5 秒检测临时占用和磁盘余量，超预算/余量不足则取消自有进程并留记录。
短时间大量写入可能在两次检测间超出预算，故启动前仍需估计真实峰值。

MCP 连接存活期间，每 60 秒维护已登记项目；比较/脚本申请空间前也维护。
退出 Codex 后没有常驻清理服务。异常退出的自动任务在失去 OS 租约并保留 24 小时后可回收；
手动分配的目录始终保持 active，直到智能体确认所有使用者已停止并 complete。
正常 complete 立即回收；显式暂存的 completed 目录默认一小时后回收。
原始样本、源码和当前产品必须放在持久目录。临时目录一旦被 case 引用为证据、输入、
产品、比较记录或交付，清理时自动保护；还可显式 protect。模糊/损坏登记、缺失 case、
改动的归属标记、目录链接/reparse point、Git 数据和扫描错误均保留并报告。

面向用户的开场白可以直接说：

> 帮我继续分析和开发。临时测试文件请自动回收，保留原软件、源码、有效证据和最终成果，磁盘空间不足时先停下相关大操作并告诉我。

智能体在调用会生成大量文件的本地工具、构建、原生 REA 工具或外部脚本前：

1. 调 rf_next_storage action=status 核对余量和现有登记；明确大操作的空间需求。
2. 用 action=allocate，填写 purpose、rebuild（如何重建）和 reserve_bytes（预期峰值字节）。
   返回 path/relative_path/id。把可重建输出、解包副本、浏览器临时资料和中间包写到这里。
3. 必要的日志、截图、bundle、实际输出及交付产物写到持久 case/成果路径，先核对完整性；
   仍有需要的临时内容先保存或 protect，不能将完整软件包不断复制到不同轮次目录。
4. 所有相关进程结束后 action=complete 并传 id；查看 reclaimed_bytes/保留原因。
   重建原始样本或重复下载前先查是否有可复用的内容。不得为绕过低空间提示调低保留线。

示例工具参数：

```json
{"project_root":"D:/Project/software-a","action":"allocate","purpose":"一次集成测试的可重建执行副本","rebuild":"用已保存的测试脚本和持久输入重新运行","reserve_bytes":536870912}
```

```json
{"project_root":"D:/Project/software-a","action":"complete","id":"<allocate返回的id>"}
```

policy 可修改 max_temporary_bytes、minimum_free_bytes、minimum_free_fraction、
completed_ttl_seconds、interrupted_ttl_seconds，按明确工作量调整，不要求用户选择专业参数。
status 只读，sweep 执行到期维护，protect 接受项目相对 paths 列表。
工具报告只统计已登记临时空间；未登记历史目录不会被算作可回收垃圾。
case status 的 storage 为轻量摘要，last_inventory/measured_at 标明上次实际统计时间。
全局指引也覆盖普通项目的大量临时构建/测试输出，storage可独立使用，无需建立逆向case。

旧聊天尚未重连时可使用绝对 CLI，在选定项目外也可运行：

```powershell
& 'D:/Project/reverse-next/.venv/Scripts/python.exe' 'D:/Project/reverse-next/scripts/next-cli.py' storage --project-root 'D:/Project/software-a' --action status
```

其他参数写 JSON 后用 --options-file 传入。登记位于项目 .rea-enhanced/disk.json，
目录有独立归属标记；跨项目卷登记位于用户 .codex/state/reverse-fusion-disk。
RF_NEXT_DISK_STATE 可显式隔离协调状态，仅用于隔离验证/自定义环境；需协调的所有进程必须使用同一位置。
复制旧登记到别的项目不会取得清理权；没有按名称收养旧 work、dist、cache 文件夹的入口。
升级安装会写入这些使用指引和第五个增强工具，新电脑通过公共安装入口取得同一行为。
