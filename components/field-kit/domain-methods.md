# 按用户要解决的问题选择方法

先确认要交付的结论、报告或实现，再按问题打开对应方法。每份方法可独立使用。混合任务可以用对账方法统一跨材料的身份和时点，再选择相关领域方法解决各自的问题。宿主可沿用已有可靠记录。

| 用户要解决的问题 | 输入线索 | 按需读取与交付 |
|---|---|---|
| 确认哪些设备或部署批次需要召回、替换或补查 | 公告、现装清单、批次用料、锁文件或 SBOM | [供应商召回与依赖影响](field-guide-supply-recall.md) → 逐对象的处置、适用依据及未知项 |
| 还原一件事在不同设备上的交接经过 | 设备日志、班次导出、偏移或校时记录 | [日志取证](field-guide-log-forensics.md) → 有原始编号和来源行的时间线、并列和不可排序记录 |
| 查云资源或 Kubernetes 的配置漂移 | 期望清单、同环境快照、`spec`/`status` 或变更记录 | [云配置核查](field-guide-cloud-config.md) → 对象和字段差异、单位换算、已观测范围 |
| 判断账号是否符合应用、目录或云资源的权限规则 | OIDC/SAML 配置、账户组关系、角色、条件和有效期 | [身份配置核查](field-guide-identity-config.md) → 逐规则和主体的配置资格、适用时点及运行证据 |
| 查数据库约束、审计配置差异或备份恢复点 | 模式、迁移、连接配置、数据库副本或备份清单 | [数据库核查](field-guide-database.md) → 结构差异、副本试验或恢复点和依据 |
| 判断存档邮件鉴权与域名对齐 | 原始 `.eml` 或完整邮件头、可信接收边界和策略 | [邮件鉴权](field-guide-email-auth.md) → SPF、DKIM、DMARC 判断和可信来源 |
| 确定 WAV 采样率、帧数、I/Q 样本或时长 | PCM WAV、同次采集说明 | [WAV 采样](field-guide-wav-sampling.md) → 字段、单位和反算，缺证的采集信息单列 |
| 找出或修正业务程序算错、失败却落账等问题 | 原程序、样本、状态起点和业务约定 | [业务代码审查](field-guide-business-code.md) → 根因、原版观察，按请求交付修复及回归结果 |
| 从可操作原件做独立实现 | 原件、运行环境、操作与输出 | [独立复刻](field-guide-independent-replica.md) → 独立工程和两侧的行为、持久化、导出及视觉对照 |
| 合并公告、主数据和流水，说明达标、差额与待核项 | 多来源台账、稳定键、截点和证据编号 | [跨材料对账](field-guide-reconciliation.md) → 确认、排除、待核台账及对应报告或图表 |
| 查发布物、声明、格式手册、离线帧、分区或工程台账 | 归档、网页、APK、plist、原始记录及匹配的版本说明 | [普通离线材料核查](field-guide-offline-materials.md) → 文件或字段差异、出处与观察边界 |

## 共用核对

- 以目标对象和证据时点限定结论。不同来源可按构建、稳定设备号、记录 ID 或可证明的时间关系关联。按原文保留编号，注明它标识的是事件、对象还是来源。
- 保留原始时间及来源。事件时间线先按目标筛选，再按绝对时间排序。排除项保留同类记录的原始编号及排除依据。关系图保存后回读实际节点、连线、方向和来源编号。
- 按同版本字段手册解释记录中的编号、值和单位，注明纳入统计的记录。遇到未确认值，保留已知小计与缺失范围。报告格式由用户的接收要求决定。
- 分区清单的 `active`、`next_boot` 是分区 ID，版本号由同一文件的版本映射得到。用户要求分区 ID 时输出 ID。缺少启动后的日志时，升级是否已启动为 `unknown`。
- 工程换算使用适用修订的公式。仅有原始读数、比例和偏移时，`raw × scale + offset` 和 `(raw + offset) × scale` 可能产生不同结果。此时工程值填 `unknown`，报告列出条件计算及缺证项。缺单位时单列单位未知，现场读数与实际现场事件分别记录。
- MV3 的 `permission_declarations` 区分必需站点、可选站点、必需 API 和可选 API。`invalid_fields` 标记格式错误。`service_worker_declaration` 提供声明路径，可与实际包成员和摘要对应。扩展启动或后台运行需要独立观察。
- 回读交付文件，核对每个字段的类型、单位、对象与范围。现有材料不足以证明和事情实际是否发生分别作答。仅在需要续接时维护案例记录。自有读数、宿主推论和官方 REA 结果标明各自身份。

## 来源正文的位置

下列相对链接用于 Field 发行模板及安装后的 `references/`，和本索引同目录。直接在仓库读取 `components/field-kit/domain-methods.md` 时，从仓库根按右栏路径定位。

| 文档 | 发行模板和安装后的正文 | 仓库源码位置 |
|---|---|---|
| Reverse Skills 取证分诊 | [取证分诊顺序](forensics-triage.md) | `skills/digital-forensics/references/forensics-triage.md` |
| Reverse Skills 取证补充 | [符号身份与时间线可比性](distilled-symbols-timeline.md) | `skills/digital-forensics/references/distilled-symbols-timeline.md` |
| 项目已有的 Flutter 说明 | [Flutter 静态观察解释](flutter-observations.md) | `components/host-adapters/review/references/flutter-observations.md` |
| 项目已有的报告说明 | [报告依据与范围](reporting.md) | `components/host-adapters/review/references/reporting.md` |

两份取证参考保留 Reverse Skills 原文和来源标识，供离线证据保全、符号匹配和时间线判读按需查阅。各 `field-guide-*.md` 的来源小节标明 Field 自有方法的依据。历史案例和外部规范供追溯，当前对象的结论以自己的材料为准。
