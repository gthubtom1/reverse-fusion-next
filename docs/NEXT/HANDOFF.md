# 重启交接：继续精简实施

当前恢复入口已更新为RESUME、FINAL-FORM.md和STATUS.autonomy_finalization；下文仅为已执行完毕的历史交接，不重新启动旧待办。

更新时间：2026-11-18。**本交接已执行完毕，保留作历史记录。当前权威结果为[SLIM-RESULT.md](SLIM-RESULT.md)、RESUME及STATUS。179项源码绑定回归核验完成，S4清理/结论已完成；没有后台任务或待继续清理。** 下文目录和恢复命令是清理前快照，不要重复删除、重新创建测试副本或把已回收路径视为现存。未提交、推送或切换托管部署，模型效果仍未建立。

恢复口令：**按 docs/NEXT/HANDOFF.md 继续精简实施。**

## 当前任务与权限

- 用户已先要求制定方案，再明确说“按方案实施”。当前实施docs/NEXT/SLIM-PLAN.md的S0→S4，不重新讨论方向、不重跑原独立审核。
- 架构：官方REA核心＋按需Reverse方法＋薄要求/平台/存储适配；不是再搭一套复刻框架。
- 项目D:/Project/reverse-next；分支fix/independent-audit-nine；HEAD仍8727a988132614a9bc042c39794c0a08db2daec2。
- **所有9项旧修复和本轮精简均未提交。不要reset/checkout覆盖脏文件。** 没有commit/push/切换用户部署的授权。
- 按AGENTS.md，当前宿主是唯一推理/编码者，不启动子代理、第二模型、付费模型实验或后台AI循环。
- 不运行旧D:/Project/reverse的安装器，不恢复旧真实目标，不改用户真实skill/AGENTS/config或复制凭据。
- 源码是editable部署，新连接会读新源码；没跑安装器不代表运行源码没有变化。
- 先读本文件、RESUME、REQUIREMENTS、PLAN、STATUS、DECISIONS；历史2.4.0资格不覆盖当前修改。

## 已实际完成

### S0 修复基线和可回退材料

- 已冻结包含原9项修复的实际脏工作区，不只是HEAD。
- state/slim-baseline-20261118/repaired-source.zip：1464文件，7,589,391压缩字节。
- SHA256：257c7fb8e90d38f0dc012e0621e181b2bb55295313a75e8b2f5e8498532a4e52。
- evidence/next/slim/baseline.json逐文件摘要；已在独立空目录解包并全部重hash一致，不只是检查zip目录。
- evidence/next/slim/mechanical.json记录还原与机械计量。归档仍须保留；不含运行包或用户凭据，不是已资格安装包。

### S1 验证纵向切片

- 新rea_enhanced/native_verification.py，只走官方公开stdio MCP：import_evidence_bundle → verify_reconstruction → export_evidence_bundle。
- 官方包、schema、Evidence/ID不改写；自有comparison.json标owned-result-index，原响应native-response.json、原bundle保留。
- kind=rea计划走现有rf_next_compare；核选中主张的左右source Evidence subject.local_path及SHA，必须对应当前original/candidate声明文件。
- 绑定Node、实际官方JS及包内执行依赖、传输实现、适配器、相关环境摘要、计划/bundle/原响应与候选内容。缺失、错候选、篡改、unknown不授予pass。
- 原生unknown在status.features[*].verification_sources中给原ID；不复制成本地unknown再resolve。
- 同一case能消费真实原生结构结果和现有Windows进程行为结果；结构维度不会满足behavioral维度。
- 新record requirement保存id/description/checks/dimensions/source/review，仍使用同一features映射；结果引用自动派生，无需重复手填技术evidence和coverage。
- 新deliver_stage保存选中已验证范围，保留剩余要求/补充/unknown，whole_product_acceptance仍not-established。
- 原五个增强入口不变；原官方255工具合同继续由原后端转发。
- 未开发coverage/obligation、设备或任意项目测试的通用适配器；这些真实结果仍独立报告，不能手填pass冒充已接入。

### S2 默认规则减负

- RULES.md、docs/AGENT-WORKFLOW.md、deployment.skill_text收敛为短合同/入口。
- 保留安装归属识别所需的原“# Reverse Fusion cross-project adapter”和“The canonical checkout is `...`”标记，不放宽用户编辑保护。
- router/runtime增加on-demand method_loading；required_reads只有RULES；原领域skill及困难材料在method_reads中按需检索。
- 新docs/DOMAIN-METHODS.md解释技术内容按需读，历史阶段/workitem/Craft/Spec控制不进入默认路径。原方法文件未删，603文件的原身份仍保留。
- README、COMPARISON、RECOVERY及活动文档目录同步。qualification.source_identity新增绑定runtime.json和新活动文档。

### S3 兼容

- 旧case-v2与原feature/evidence/coverage接口保留；status投影当前短合同但不重写旧case字节，也不将旧pass升级为原生pass。
- 显式搬家使旧检查、完整/阶段交付和复用失效，保留原话和补充；原生subject路径不偷偷重绑定。
- 旧9项修复及磁盘/租约设施继续保留，未无谓重写安装/存储模块。

## 测试实际状态：最终179已通过

- 原9项修复基线：164项隔离回归通过，真实Ghidra启动项未执行，证据evidence/next/audit-repairs。
- 本轮首9项纵向测试8通过，1项测试用了原生unknown不适用的scope参数；已改为正式合同支持的关联方式。
- 第一177全套发现短skill丢失归属标记、公共字节超限、隔离复制漏新文档；已修正，失败证据保存在evidence/next/slim/attempts。
- **第二177项全套已通过，0 failures/errors，149.359秒。** 包含原生unknown、错候选/篡改、取消、搬家、Windows/web、原官方目录、临时home安装/卸载/回退。
- 随后补了status原生来源/unknown投影、同一增强MCP入口真实原生验证，以及原版被候选路径替代反例，最终应179项。
- **交接写入期间最终179项已完成并核验：0 failures/errors，197.438秒。** 85文件canonical source_identity与当前工作区及隔离副本完全一致。正式结果evidence/next/slim/regressions.json/txt，包含实际证据摘要。
- 后台任务btnpddvrh已正常退出；当前没有后台验证待等待或轮询。原输出D:/tmp/claude/849d04975e14585d/1cb13426-70d7-41a0-a55f-b46f249934df/tasks/btnpddvrh.output。
- 最终原生原响应/bundle、owned比较与阶段交付保存在evidence/next/slim/representative-test.json；官方目录证据protocol-qualified.json。三份用户入口摘要已重新核对不变，见deployment-preservation.json。
- 仍排除tests_next.test_mcp.LiveMCP.test_actual_native_provider_and_new_server_bundle_roundtrip（真实Ghidra）。原生ZIP检查/compare/verify则确实执行，不是mock。

## 隔离目录、工具和恢复命令

主验证区：D:/tmp/reverse-next-slim-55fuatfp。

- source/：独立源码、Node、REA包/依赖与venv；Chrome仅选本机已有路径，没有导入真实用户配置/Ghidra。
- regression.json / regression.txt：最终tests==179、failures/errors为空且日志正常结束，已归档；早先177属于上一轮，不作为最新源码资格。
- source-identity.json：运行前拷贝文件的原始SHA；evidence/next/slim/isolated-source-at-handoff.json保存交接时副本。
- deployment-before.json：用户入口文件的摘要，收尾重新核对；不保存内容。
- source/evidence/next/slim/representative-test.json：最终集成测试成功后保存原生原响应/bundle、原生及owned回执、阶段交付和剩余要求。临时原路径保留为历史，不改写成可复用当前项目证明。
- source/evidence/next/s2/protocol-qualified.json等：实际官方目录保留/260工具及stdio证据；按需归档本轮来源，不拿旧发布文件替代。

如179结果缺失、失败、中断或不绑定当前源码，在没有同一旧测试进程仍写该source时重跑；脚本会刷新独立副本，不改真实配置：

```bash
python -I -B state/slim-tests.py D:/tmp/reverse-next-slim-55fuatfp --full
```

长命令后台执行，等完成通知，不开轮询/新模型。脚本完整备份在evidence/next/slim/support/slim-tests.py；另有slim-measure.py、slim-record-probe.py。state脚本不是产品运行入口。

交接源码的正式source_identity（85文件）与待办在evidence/next/slim/handoff-checkpoint.json；当前源码与检查点、隔离测试副本已核对一致。连续性文档的收尾变化不算运行源码变更。

## 已有机械收益数据，不是模型效果

- 公共自有合同（RULES＋工作流＋渲染skill）：17,253 → 6,014 UTF-8字节，约减少65%。安装路径更长会增加skill字节，测试还检查独立副本路径下≤6KiB。
- 困难APK默认必读：10文件/93,161字节 → 仅RULES 2,801字节；专业方法未删，按需另读，不把按需内容算成消失。
- 同一有限计数/错误处理fixture的实际轨迹：总API调用7→5，显式record5→3；两者均实际比较4个步骤且reviewed-delivery。
- 回传体积32,428 → 27,179 bytes；单次耗时0.687 → 0.766秒，未证明速度提升。
- 项目API边界采样磁盘27,397 → 22,697 bytes；不是瞬时磁盘高水位/进程RSS，没有完整峰值证明。
- 原始轨迹：evidence/next/slim/baseline-trace.json、candidate-trace.json。全部无额外模型调用；同模型质量/成本净收益尚未建立。

## 下一宿主按顺序收尾

1. 读取已归档的179最终结果及85文件源码身份；若源码自交接后未改，不为恢复而盲目重跑；有新修改才按影响验证。
2. 最终回归json/txt、确切源码身份、真实native/owned代表回执及官方目录证据已归档evidence/next/slim，收尾报告引用它们，不复用旧2.4.0发布资格。
3. 用户skill/AGENTS/config摘要已与deployment-before核对，见deployment-preservation.json；清理结束后再核对一次。
4. 确认测试和子进程结束，回收本轮隔离大副本并记录字节/文件数；保留S0源码归档、失败历史、最终证据。可能待回收：
   - D:/tmp/reverse-next-slim-55fuatfp/source、coordinator、temp等；保留小型报告/脚本亦可。
   - D:/tmp/reverse-slim-native-foo2sqex（最早真实native探针）。
   - D:/tmp/reverse-slim-rollback-_cv0dlk5及D:/tmp/reverse-slim-rollback-bdvwfz06（两次实际归档解包）。
   - 本轮trace专用coordinator-baseline/candidate，若存在先核归属及无活动者。其他旧临时目录不扩大清理范围。
5. 更新SLIM-PLAN、CURRENT-STATE、RESUME、STATUS、JOURNAL并给用户白话结果；目前S4未完成，不写已发布/已部署/模型更强。
6. 不提交、不推送、不运行真实用户安装或切换入口。新版公开clone安装/真实Ghidra/设备/跨机器以及模型实验均尚未做；分别说明边界。

## 本轮新增/主要改动

- rea_enhanced/native_verification.py（新）、workflow.py、comparison.py、server.py、relocation.py、qualification.py、deployment.py。
- reverse_fusion/mcp_probe.py：可取消request，仍用原OS进程归属/清理。
- components/reverse-core/router.py、runtime.json；RULES、AGENT-WORKFLOW、DOMAIN-METHODS、README、COMPARISON、RECOVERY及ACTIVE-DOCUMENTS。
- tests_next/test_slim.py（新）、test_domains.py、test_qualification.py。
- 旧9项修复仍在同一脏工作区：涉及storage/disk/providers/operations/web/cli等，不能当作本轮无关改动丢弃。

之前原9项发现已按用户要求用ReportFindings全部标fixed，无需重新报告那9条。当前不是新一轮独立审核。
