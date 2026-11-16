# 唯一安装入口：Windows x64 / Codex

先读CURRENT-STATE.md确认本版资格。完整核心为Reverse方法、固定Node、官方REA、独立Frida绑定和增强入口。没有Craft，不强制Spec，不启另一个模型或账号。

把本版放长期保留的独立目录；Python 3.11+，执行：

```powershell
powershell -NoProfile -File .\scripts\install.ps1
```

安装器创建仓库.venv和固定Python依赖，按摘要从固定来源取得Node/REA/Frida/WABT/JADX；npm按锁文件下载且不运行生命周期脚本。随后保存本机工具路径。Ghidra/Java、浏览器、设备、ILSpy和其他provider按目标需要，路径存在不等于实际操作通过；缺少工具不会冒称该类目标可验收。

唯一仓库是 https://github.com/gthubtom1/reverse-fusion-next ，默认分支main。
不要从旧reverse-fusion仓库的codex/rea-next分支安装。公开release-check要求
当前测试与工作流合同、真实工具记录和远端克隆安装证明相符；不是只读旧pass标记。

安装与providers --refresh还会生成skills/tool-index.md/.json，供保留的领域方法读取；索引区分路径发现与实际操作资格。核心doctor会将缺失/变动的Node Frida绑定判为不完整，不能用另一个Python包冒充。

REA原包的全部文件在bootstrap及doctor中和固定下载档逐一核对；原入口存在不能
掩盖缺失执行模块。独立Frida层在重装前实际加载，不以binding文件单独冒充可用。
原包损坏时保留报错；仅重新提取本checkout的受托管vendor/rea/package，不能覆盖别处REA。

默认只管理当前Codex的reverse-fusion用户技能、全局AGENTS托管段、一个reverse-fusion-rea MCP。保留无关配置与凭据。已有另一checkout的托管入口时显式指定旧绝对路径：

```powershell
.\scripts\install.ps1 -ReplaceFrom 'D:\Project\reverse'
```

安装实际连接登记命令并运行目标无关操作，失败恢复旧段。输出rollback_receipt仅含托管段，保存在state/migrations。回退：仓库Python -m rea_enhanced rollback --receipt '<回执绝对路径>'。

隔离安装用-HomeDirectory '<临时目录>'；只准备运行包用-PrepareOnly。检查入口：仓库Python -m rea_enhanced mcp-check。同名非托管条目或被改过的托管内容拒绝覆盖。安装回执不等于软件复刻验收。

客户端可能重写TOML并丢弃注释标记。旧版迁移只有在显式ReplaceFrom且登记的命令、参数、目录、超时和环境完全匹配旧版时，才允许接管那两段；不接受其中的额外配置。新版在用户技能/全局入口归属一致时可识别同一精确登记，连接检查及回退也支持该形式。原始托管字节只保存在本地恢复回执，无关配置不备份、不改写。

完成后重连工具或新建聊天；旧桌面连接不一定自动切换。其他宿主可适配相同stdio和指引，但本安装器只管理Codex；未知宿主需核对实际接口。历史四组件安装脚本不可运行。
