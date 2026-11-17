# 跨项目

MCP缺席时使用open/status返回的component_entries.enhanced_cli绝对入口。
它固定共享仓库导入位置，即使成果目录有同名Python模块也不会误调用目标代码。
不要在成果目录用裸python -m猜测共享工具的导入来源。

共享checkout仅工具/技能，project_root始终是当前成果项目绝对路径。open恢复同case，读返回领域与官方方法。case-v2、原bundle、比较输出都在成果目录。CLI默认当前目录，不为方便切到工具库写成果。

空目录仍由全局入口找到共享工具。v1 case不隐式升级；明确选择新case引入原材料。普通开发不建case，需要调查可在项目中按需建立。见AGENT-WORKFLOW。

三级存储登记也属于各自成果项目，按DISK-MANAGEMENT.md生成时分类、操作边界审查。
多个项目只共享按卷预留协调，不共用或认领彼此的缓存/临时输出。
