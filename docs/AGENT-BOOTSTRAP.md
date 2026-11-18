# 唯一安装入口：Windows x64 / Codex

## 稳定安装

日常安装使用[已验收的 2.4.0 源码](NEXT/STATUS.json)，固定提交 `608170da42e391f8093025b59a8245b48ed06183`。`main` 已包含未做运行验收的自主版；包版本号同为 `2.4.0`，以 Git 提交区分。只想查看自主版，去 [GitHub 源码预发布页](https://github.com/gthubtom1/reverse-fusion-next/releases/tag/autonomy-20261118) 下载源码 ZIP 和 SHA256 清单，无需安装。

适用于 Windows x64 / Codex，需要 Git 和 Python 3.11+。首次安装使用一个新的长期保留目录。已有托管入口的用户先读下方迁移和回退说明，不要覆盖原目录。

```powershell
$installRoot = 'D:\Project\reverse-next-2.4.0'
$qualified = '608170da42e391f8093025b59a8245b48ed06183'
if (Test-Path -LiteralPath $installRoot) { throw 'Choose a new checkout directory.' }
git clone --no-checkout https://github.com/gthubtom1/reverse-fusion-next.git $installRoot
if ($LASTEXITCODE -ne 0) { throw 'Clone failed.' }
git -C $installRoot switch --detach $qualified
if ($LASTEXITCODE -ne 0) { throw 'Could not check out the qualified source.' }
```

首次安装在同一个 PowerShell 窗口继续；运行安装器前再次核对提交：

```powershell
$actual = git -C $installRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $actual -ne $qualified) { throw 'Unexpected source commit.' }
powershell -NoProfile -File (Join-Path $installRoot 'scripts\install.ps1')
```

安装器创建仓库.venv和固定Python依赖，按摘要从固定来源取得Node/REA/Frida/WABT/JADX；npm按锁文件下载且不运行生命周期脚本。随后保存本机工具路径。Ghidra/Java、浏览器、设备、ILSpy和其他provider按目标需要，路径存在不等于实际操作通过；缺少工具不会冒称该类目标可验收。

支持分段的固定资源采用有界并发下载；分段断流/短读只重试失败段，保留完整段。
分段位置、ETag、长度和最终完整文件摘要仍逐项验证，身份或摘要变化不会当作网络重试放行。

唯一仓库是 https://github.com/gthubtom1/reverse-fusion-next ，默认分支main。
不要从旧reverse-fusion仓库的codex/rea-next分支安装。公开release-check要求
当前测试与工作流合同、真实工具记录和远端克隆安装证明相符；不是只读旧pass标记。

安装与providers --refresh还会生成skills/tool-index.md/.json，供保留的领域方法读取；索引区分路径发现与实际操作资格。核心doctor会将缺失/变动的Node Frida绑定判为不完整，不能用另一个Python包冒充。

REA原包的全部文件在bootstrap及doctor中和固定下载档逐一核对；原入口存在不能
掩盖缺失执行模块。独立Frida层在重装前实际加载，不以binding文件单独冒充可用。
原包损坏时保留报错；仅重新提取本checkout的受托管vendor/rea/package，不能覆盖别处REA。

默认只管理当前 Codex 的 `reverse-fusion` 用户技能、全局 AGENTS 托管段和一个 `reverse-fusion-rea` MCP，保留无关配置与凭据。迁移已有托管入口时，先完成上面的克隆和固定提交步骤，再在同一个 PowerShell 窗口执行下列命令（把 `-ReplaceFrom` 换成实际旧 checkout 的绝对路径）：

```powershell
$actual = git -C $installRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $actual -ne $qualified) { throw 'Unexpected source commit.' }
powershell -NoProfile -File (Join-Path $installRoot 'scripts\install.ps1') -ReplaceFrom 'D:\Project\reverse'
```

安装实际连接登记命令并运行目标无关操作，失败恢复旧段。输出rollback_receipt仅含托管段，保存在state/migrations。回退：仓库Python -m rea_enhanced rollback --receipt '<回执绝对路径>'。

隔离安装用-HomeDirectory '<临时目录>'；只准备运行包用-PrepareOnly。检查入口：仓库Python -m rea_enhanced mcp-check。同名非托管条目或被改过的托管内容拒绝覆盖。安装回执不等于软件复刻验收。

客户端可能重写TOML并丢弃注释标记。旧版迁移只有在显式ReplaceFrom且登记的命令、参数、目录、超时和环境完全匹配旧版时，才允许接管那两段；不接受其中的额外配置。新版在用户技能/全局入口归属一致时可识别同一精确登记，连接检查及回退也支持该形式。原始托管字节只保存在本地恢复回执，无关配置不备份、不改写。

完成后重连工具或新建聊天；旧桌面连接不一定自动切换。其他宿主可适配相同stdio和指引，但本安装器只管理Codex；未知宿主需核对实际接口。历史四组件安装脚本不可运行。

2.4.0安装同步三级存储指引与rf_next_storage的review/reuse/promote接口，无需另装清理程序。
生成时区分持久、可复用和一次性输出；在操作或验证边界由宿主判断二级keep/release，三级完成即回收。
每项目二/三级合计默认4GiB，其中二级预算2GiB；按卷保留至少2GiB或2%并协调预留。
一级不降级，所有原始输入和有效证据保留。连接内周期维护只作三级兜底，不自动按年龄删除二级，
退出后无常驻任务。宿主直接命令须按DISK-MANAGEMENT.md把大输出写入适当分配目录。
旧2.3.0 scratch调用兼容，旧目录不按名称自动清理，升级也不扫描删除无关项目。

## 卸载与新旧隔离

本版只登记一个reverse-fusion-rea，内部提供官方REA和rf_next增强工具。
新版不登记reverse-fusion-craft，不另装第二份同用途REA入口。
手工另装的rea或Craft插件不属于本仓库管理范围，先识别归属，不能盲删。

只卸载当前checkout托管入口（保留源码、运行包与成果）：

```powershell
.\.venv\Scripts\python.exe -m rea_enhanced uninstall
```

卸载严格检查owner与托管内容，只移除用户技能、AGENTS段及对应MCP段，
保留其它MCP、模型设置和凭据。已被用户改动的托管内容拒绝覆盖。
随后按顶部install.ps1重装，检查配置里只有选定新版登记，技能/AGENTS指向同checkout，
并实际连接原REA与增强工具。CLI uninstall不负责关闭其它聊天的后台。

重要：配置迁移不等于旧聊天内存连接已关闭。安装报告明确要求客户端重连；
只有真实连接与进程观察才能判断。需要清理旧后台时先关闭相关旧聊天/工具连接，
或在用户授权后仅终止由旧绝对目录的MCP启动器派生且身份仍匹配的进程树，
保留其它工具、目标程序及新版连接。不终止整个Codex，也不按python/node名字批量关闭。
重连后核旧目录后台为零，再以新聊天实际工具调用确认；现有聊天显示的旧工具名
可能仍是旧目录缓存，不能把它当成当前配置，也不能冒称它已自动换成新版。
