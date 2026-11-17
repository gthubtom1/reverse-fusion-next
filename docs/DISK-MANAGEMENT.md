# 生成时分级，操作结束时清理

2.4.0在磁盘生命周期上增加三级用途。智能体先决定文件用途，再选择输出路径；
清理时读取登记的用途和活动状态，无需反复根据文件名猜测。普通开发也适用，无需建立逆向case。

| 等级 | 用途 | 新分配目录 | 保留规则 |
|---|---|---|---|
| 一级 persistent | 原始材料、源码、有效观察、证据、交付和恢复资料 | `.rea-enhanced/persistent/<id>` | 自动维护和边界审查均保留，没有降级删除入口 |
| 二级 reusable | 有具体后续用途、可以重建的缓存或中间材料 | `.rea-enhanced/reusable/<id>` | 完成后保留；复用前核身份/内容/声明输入，宿主在操作边界决定继续保留或释放 |
| 三级 disposable | 本轮执行副本、测试输出、浏览器临时资料等 | `.rea-enhanced/scratch/<id>` | 所有使用者停止并complete后立即回收；必要内容先保存到一级 |

原软件、源码、证据和成果可以继续使用当前项目的正常目录，不要求搬进隐藏目录。
这里的三级路径用于新申请的受托管空间；旧调用不传tier时仍分配三级scratch。
已有项目、未登记目录和未知材料原样保留，不按work/dist/cache名称收养或批量删除。

## 清理时机

以自然工作边界为主：一个有意义的操作批次完成、验证完成、切换阶段、任务结束、
中断后恢复，或下一次大写入前发现空间压力。无需每条命令后都登记、扫描和打断分析。

三级由complete即时回收；显式暂存的已完成三级可在边界review时提前回收。
二级由当前宿主模型根据下一步需要判断：有明确近期用途则keep并记录原因，
确定可重建且无后续用途则release并记录原因，已成为长期资料则promote提升一级。
review返回实际决定及待审列表，不会启动第二个AI或推断未登记文件的用途。
普通operation-end/verification-end只提示到期的二级；阶段切换、任务结束、空间压力和恢复时
审查可复用层整体，避免每一批操作都重复询问同一缓存。宿主有新判断时仍可主动提交决定。
空间不足时先审查可回收材料，再决定是否启动大操作；不为继续运行降低保留线。

连接存活期间每60秒的维护只作兜底：清理符合既定规则的三级，不会因二级超过一天就删除。
二级默认24小时提示重新评估复用价值，真正释放仍需宿主明确决定。
退出Codex后没有额外常驻清理程序。手动active目录无论过多久都保留，
必须由宿主确认所有使用者/进程停止后complete；review不会代替这项确认。

## 分配、复用与审查

大操作前先用status确认余量和登记，再allocate声明purpose、rebuild、reserve_bytes和tier。
默认单次预算256MiB；智能体按真实峰值调整，不要求零基础用户选专业参数。

三级示例：

```json
{"project_root":"D:/Project/software-a","action":"allocate","tier":"disposable","purpose":"本批集成测试执行副本","rebuild":"用已保存的脚本和持久输入重新运行","reserve_bytes":536870912}
```

二级示例，reuse_key应包含工具/格式/版本等实际身份；input_paths列出影响结果的项目相对文件：

```json
{"project_root":"D:/Project/software-a","action":"allocate","tier":"reusable","purpose":"后续多个检查复用同一解码结果","rebuild":"用tools/decode.py重新解码inputs/sample.bin","reserve_bytes":1073741824,"reuse_key":"decode-format-v2-tool-v1","reuse_reason":"下一批三个功能检查仍需要同一解码结果","input_paths":["inputs/sample.bin","tools/decode.py"]}
```

所有使用者停止后complete；二级此时保存内容摘要和声明输入摘要，一级继续保留，三级回收：

```json
{"project_root":"D:/Project/software-a","action":"complete","id":"<allocate返回的id>"}
```

后续action=reuse传id，检查声明输入和保存内容未变后取得active使用权；使用完再次complete。
输入或内容变化时复用失败，保留材料供检查，按新的身份/依据重建。
生产期间声明输入发生变化时，该二级完成使用但标记为失效，后续reuse拒绝复用；
宿主仍可在操作边界判断保留检查或release，避免失效材料永远停在active状态。
只核对已经声明的输入；遗漏的外部服务、工具配置、版本等依赖仍由宿主识别并纳入身份。
缓存存在、脚本退出零或摘要一致，都不代表功能比较通过。

自然边界先review读取待审列表，再按当前任务给出有理由的决定；可以在同一次调用传决定：

```json
{"project_root":"D:/Project/software-a","action":"review","boundary":"stage-change","decisions":[{"id":"<二级id>","decision":"keep","reason":"下一阶段仍要用同版本数据验证三个接口"}]}
```

```json
{"project_root":"D:/Project/software-a","action":"review","boundary":"verification-end","decisions":[{"id":"<二级id>","decision":"release","reason":"相关验证已结束，持久证据完整，后续可按登记脚本重建"}]}
```

boundary支持operation-end、verification-end、stage-change、task-end、space-pressure和resume。
keep/release只适用于二级，一级没有释放或降级入口。
promote接受已完成且未被引用的二级/三级id，移动到一级专用目录并返回新路径；
后续使用者须采用新路径。已被case或显式保护引用的路径保持稳定，先保存持久快照，避免移动破坏引用。
二级完成后可直接提升。三级中意外发现有用事实时，优先在complete前保存持久材料；
确需保留完整目录时complete可传cleanup=false，随后立即promote，期间仍受completed保留时间约束。
默认cleanup=true，已回收的三级目录没有可提升的文件。

## 预算与保护优先级

默认每项目二级与三级合计临时预算4GiB，其中二级预算2GiB；一级不属于自动淘汰预算。
同一用户多个Codex/MCP/CLI项目按卷加锁协调预留，各磁盘保留至少2GiB或总容量2%，取较大者。
超过预算时停止新的申请并请求边界审查，不自动牺牲有效证据或仍有价值的缓存。
预留是保守的并发协调，监测为软限制，任意外部程序的写入不受操作系统硬配额约束。

活动OS租约、手动active、当前case引用和显式protect优先于清理决定。
归属标记/登记不明、缺失case、链接/reparse point、Git数据或扫描错误均保留并报告。
经过摘要核对的不可变证据快照允许回收临时来源；快照缺失或损坏则保留尚存来源供恢复。
事件历史里的路径是追溯信息，不自动形成永久文件依赖。

增强比较逐场景回收执行副本，两侧TEMP/TMP/TMPDIR分离；实际退出码、输出、
按内容摘要保存的文件效果、必要截图和原生REA bundle继续保存。
record execute把TEMP/TMP/TMPDIR/RF_NEXT_SCRATCH指向独立三级目录，结束回收；
脚本须主动使用这些位置，artifacts声明不会改写硬编码输出路径。
自有工作约每0.5秒监测临时预算和磁盘余量，超限取消相关自有进程并留记录。
短时间突发写入可能超过软限制，启动前仍须估计峰值。宿主直接命令及原REA工具
要把可重建大输出明确写到已分配路径，避免每次修改重复制完整软件包。

policy支持max_temporary_bytes、max_reusable_bytes、minimum_free_bytes、minimum_free_fraction、
completed_ttl_seconds、interrupted_ttl_seconds和reuse_review_seconds。
status只读；sweep执行既定维护；protect接受项目相对paths。
报告覆盖已登记三级，tier_bytes显示已测分级占用，last_review保存最近边界判断；
一级维护不扫描庞大持久树，返回bytes=0、measured=false表示未测，不能解读为空目录。
case status中storage仍是轻量摘要，measured_at标明上次实际统计。

登记位于项目`.rea-enhanced/disk.json`，独立归属标记验证当前项目与id；
跨项目协调位于用户`.codex/state/reverse-fusion-disk`。
RF_NEXT_DISK_STATE用于隔离验证或自定义环境，需要协调的进程须使用同位置。
旧2.3.0登记保留并按disposable解释，不隐式迁移或认领其他目录。

旧聊天尚未重连时可用绝对CLI，其他参数写JSON后用--options-file传入：

```powershell
& 'D:/Project/reverse-next/.venv/Scripts/python.exe' 'D:/Project/reverse-next/scripts/next-cli.py' storage --project-root 'D:/Project/software-a' --action review --options-file '<参数JSON的绝对路径>'
```

面向用户的白话补充即可：

> 文件生成时请分清必须保留、可能复用和用完即删。每批操作或验证结束时检查清理，保留原软件、源码、有效证据和成果，空间不足时先处理相关临时输出。
