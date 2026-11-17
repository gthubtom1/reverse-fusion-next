# 恢复

开发从NEXT/RESUME.md和STATUS.json恢复，按唯一next_action。旧RF检查点是历史，不重启旧任务。

成果从实际采用的可靠任务记录恢复；使用可选case时再status读取原话、补充、checkpoint、证据、unknown、检查和下一步。index只发现case，不是第二权威。用过原REA会话则恢复其原bundle；不为恢复而强制启动REA或覆盖旧记录。v1 case默认只读，选择新case明确导入有依据材料。外部assessment在搬家后保留历史观察但失去当前适用性，reviewed_delivery失效；重新核对对象和环境后再审查。

中断不算通过，保留原输出，用新目录再比较。检查文件锁防并发、expected_revision防旧状态覆盖。相关变化使旧结果失效；不变失败需新信息，预算耗尽回分析或记理由调整。

工具失败先记实际错误、确认自有进程清理再换方法。路径失效providers --refresh和mcp-check后实测需要的操作。缺工具仅阻断相关功能。

恢复后在适当批次边界用storage review boundary=resume查看已登记分级空间与待审缓存。
先确认旧使用者已停止，再complete手动active目录；恢复动作不把active视为垃圾。
二级重新reuse前核对输入/内容，失效时保留材料并有据重建；一级和有效证据继续保留。

成果文件夹换路径／电脑时，先停止原位置和副本的全部使用者，完整复制成果（包括隐藏目录及case-records）。智能体从原status.component_entries.enhanced_cli读取共享环境解释器和脚本的两个绝对路径，在副本目录执行；若原位置已不可读，则从当前共享checkout定位对应文件。不要在成果目录查找同名相对脚本：

```bash
"[共享checkout绝对路径]/.venv/Scripts/python.exe" "[共享checkout绝对路径]/scripts/next-cli.py" relocate --project-root "[新成果绝对路径]" --from-root "[case中原project_root原文]" --reason "[搬迁原因]" --inactive
```

命令核对复制的证据、产品、比较回执和存储归属，拒绝活动OS租约；只重绑定副本case与归属标记并登记新协调位置，原始状态保存在副本.rea-enhanced/relocations回执。旧比较、覆盖审查、交付与操作复用失效；重新核对环境和计划中的旧绝对路径，再比较。缓存须按新环境重建；已完成三级仍遵循正常清理规则。其他机器原位置的活跃进程无法从本机探测，--inactive表示已确认停止。失败的校验不改变原账本，报告的写入失败回退所改文件。

精简候选兼容原case-v2，无隐式格式转换。status只读投影当前短合同与新鲜检查，不重写旧route/证据；旧pass不会升级为原生pass。requirement与旧feature仍在同一features映射，原话和补充不迁移丢失。原生未知保留原bundle/ID，不在本地resolve。搬家同时使阶段交付失效，须重新观察新位置的原生subject而非改写原ID。

本轮源码回退材料见evidence/next/slim/baseline.json，归档state/slim-baseline-20261118/repaired-source.zip保存未提交9项修复后的实际字节。先核归档摘要、还原到新空目录并逐文件核对；只选择本轮改动恢复，保留新证据和无关新增文件，不用git reset --hard替代。该归档不含用户凭据或运行包，不是完整可安装发布包。

安装失败恢复托管段；异常中断可用prepared回执rollback。托管内容已改时拒绝覆盖，留待检查。回退保留新加的无关配置。旧checkout和基线标签保留，不删仍被其他聊天使用的目录。回退后重连。
