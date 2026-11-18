# GitHub源码预发布：自主支持最终形态

日期：2026-11-18。用户明确要求提交、推送并发布GitHub，暂不部署；这覆盖此前仅本地定档、不提交的限制。

## 发布方式

- 仓库：https://github.com/gthubtom1/reverse-fusion-next
- 开发分支：fix/independent-audit-nine
- 预发布标签：autonomy-20261118
- GitHub发布页：https://github.com/gthubtom1/reverse-fusion-next/releases/tag/autonomy-20261118
- 形式：明确标为prerelease的源码快照，不作为新的正式稳定版或GitHub Latest。
- 原包版本元数据保留2.4.0；快照标签用于区分本轮改造，不伪装成重新通过2.4.0发布门。
- 发布操作推送分支并建立指向 `main` 的 PR，当时未合并、不替换已有基线。
- 本机托管skill/AGENTS/MCP、运行包和凭据不改；editable源码修改影响新连接这一已有事实不变。

## 内容与验证

提交包含原9项审核修复、精简实现、17项静态复核修复、最终自主支持形态、回归用例源码及相应历史/当前证据。

当前功能源码对应evidence/next/autonomy-final/validation.json的65份静态源码身份；发布阶段只调整状态/说明及源码归档。静态检查通过不等于运行验收，新增用例未执行；历史179项测试仅对应较早源码。没有为发布安装依赖、运行真实目标、启动provider/MCP或进行模型对话实验。

提交前对本轮改动进行常见GitHub/API密钥、AWS密钥与私钥头模式检查，无命中；这只是有限模式检查，不是完整秘密审计。ignored的state、用户配置、venv、运行包和下载缓存不进入Git提交。

## 源码资产

发布源码ZIP从实际Git提交导出，附SHA256清单；不上传含运行包/凭据的环境备份。普通GitHub源码下载也保留。此前本地定档ZIP与回退包继续保留，不把它们误称为已资格安装包。

## 当前状态

GitHub 预发布已实际创建并核对：`isPrerelease=true`、`isDraft=false`，标签指向源码提交 `5bc870b8b7c0723641efd4080cb596ea89230f38`。发布时 [整合 PR](https://github.com/gthubtom1/reverse-fusion-next/pull/1) 打开；随后由 GitHub 核实已合并，`main` 的合并提交为 `5816a814bd3d032d5744de726eef5a710adb4999`（2026-11-17 21:12:29 UTC）。合并没有移动标签，也不改变预发布的运行验收结论。日常安装仍按[安装指南](../AGENT-BOOTSTRAP.md#稳定安装)固定到先前通过验收的提交。

源码ZIP：reverse-fusion-next-autonomy-20261118-source.zip，8,247,938字节；SHA256：91be45c7b4c11efccd2f7e527223aac65c1acdc61001e6b7860b0e20040ac1be，与GitHub资产digest一致。SHA256SUMS.txt和source-manifest.json均上传完成。

evidence/next/publication 保存发布当时的页面、标签和资产身份核对；其中 PR 状态和 CI 记录是发布时快照。发布后的记录提交只补充元数据，不移动已发布标签或修改功能源码。没有部署动作。
