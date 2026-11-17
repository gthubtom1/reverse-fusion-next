# 一个增强REA连接

名称reverse-fusion-rea，命令为本仓库.venv Python -m rea_enhanced mcp，cwd为checkout。保留255个原REA工具/prompts，新增rf_next_case_open、rf_next_case_status、rf_next_case_record、rf_next_compare、rf_next_storage，共260工具。

storage在同一第五入口内管理persistent/reusable/disposable三级空间、保护与预算，新增review、
reuse、promote而不增加MCP或第二模型。操作边界由宿主判断二级保留/释放，复用核内容和输入；
MCP连接内每分钟维护只作三级兜底，不按年龄自动删除二级。没有额外系统常驻服务，
也不通过文件夹名称猜测未登记文件用途。实际时机和参数见DISK-MANAGEMENT.md。

mcp-check实际初始化、分页目录、binary_session、Frida枚举与进程清理。登记不证明旧桌面聊天热更新，需实际重连。宿主仍唯一推理与编码。

增强会话绑定启动时的工作流代码和核心固定清单。更新后旧连接的增强操作返回
needs-reconnect，不静默用内存中的旧代码处理新版记录；重连或先用绝对CLI入口继续。
官方原工具身份仍由同固定包保持，更新provider后也要重连并实测。

providers --refresh保存路径，CLI/MCP共用；路径不证明目标工具操作成功。原REA证据导出到成果case，重启原样导入。按目标接其他工具，不把全部provider强制开机。
