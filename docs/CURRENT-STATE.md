# 当前状态：Reverse Fusion Next 2.4.0

生成时三级存储与操作边界审查已实现、资格通过、本机安装并发布。
独立仓库：https://github.com/gthubtom1/reverse-fusion-next ，默认分支main。
本轮冻结实现：608170da42e391f8093025b59a8245b48ed06183。后续收尾记录不改变已测试的源码与公共合同。

当前架构是Reverse领域方法＋官方REA6.9.0＋自有增强层；当前宿主唯一推理编码。
增强层学习Craft的有界比较/修正原则后独立实现，Craft无运行依赖，Spec可选。
一个reverse-fusion-rea MCP保留255个官方工具和五个增强入口，共260工具。

一级persistent保存持久材料；二级reusable有身份、声明输入、内容摘要和后续用途；
三级disposable完成即回收。review在操作/验证结束、阶段切换、恢复或空间压力节点执行，
宿主以理由决定二级keep/release；二级年龄只提示，一级不降级，活动/证据保护优先。
默认二/三级合计4GiB、其中二级2GiB，跨项目按卷协调预留。一级维护不扫描大树。
完整行为、参数与软限制见DISK-MANAGEMENT.md。宿主直接工具仍须采用分配的输出路径。

148项本地源码绑定检查通过，同源码从GitHub默认分支独立clone，经公共安装器取得自己的
固定运行包，再通过148项；没有借用开发目录运行包/缓存，临时用户配置精确回退。
本次新安装checkout已回收719773386字节、16229文件。
公开安装全流程耗时759.438秒（包含下载、安装、测试和回退）。
真实stdio MCP证明分级、keep/release、复用、二/三级提升一级、实际回收及原始/持久摘要不变；
绝对CLI从其他空目录执行通过。运行、安装包元数据、仓库版本均2.4.0。
本机当前托管skill/全局AGENTS/登记命令已更新，require-deployed release-check通过。
回执：evidence/next/tiered-storage；完整检查：evidence/next/s6/engineering-tests.json；
独立安装：evidence/next/final-audit/remote-install.json；需求验收：NEXT/ACCEPTANCE.json。

2.2.0的观察快照、紧凑状态、行动诊断、可选脚本计量/复用、候选身份和按变化验证继续保留。
2.3.0的64MiB及默认60秒周期实测是历史证明，当前新增机制使用本轮独立绑定的结果。
旧样本约61.66GiB的统计包含超长路径错误，属于成功读取部分；没有恢复任务或批量删除旧目录。

架构帮助、成本与困难目标依据见NEXT/ARCHITECTURE-REVIEW.md。当前没有同模型同工具A/B，
工程检查不等于任意目标成功，商业壳/VM/反调试目标仍须逐项建立实际证据。
安装唯一入口AGENT-BOOTSTRAP.md，白话使用BEGINNER-GUIDE.md。已有聊天清单可能缓存，
重连或新聊天加载新版；绝对CLI可读取当前实现，不关闭无关聊天、程序或MCP。
