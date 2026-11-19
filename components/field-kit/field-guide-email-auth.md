# 存档邮件的 SPF、DKIM 与 DMARC 判读

## 输入

获取原始 `.eml` 或完整头部导出、当时的接收边界或可信 `authserv-id` 清单、适用时点的鉴权策略。若需要核对接收端实际处置，取对应邮件的服务器日志或投递回执。记录原始头部的行号及折行范围。

## 判读

1. 定位可见 `From` 的域。核对 `Authentication-Results` 来自哪一个接收方及可信边界，再读该结果中的 SPF、DKIM 和 DMARC 记录。同名头部可重复出现。缺少可信接收边界或归属证明时，把记录中的文字与可信鉴权结论分开。
2. 对 SPF，核对结果及其适用的信封发件域，空反向路径按 RFC 7208 的 MAIL FROM 身份规则核对，应为 `postmaster@<HELO 域>`，单独一条 HELO 通过记录不足以判定 DMARC 的 SPF 路径。对 DKIM，逐条核对报告为 `pass` 的签名域 `header.d`。分别比较各路通过的身份域与可见 `From` 域。严格对齐要求域相等，宽松对齐使用接收端当时采用的组织域口径。RFC 9989 使用 DNS 树查询，历史记录可能按 RFC 7489 使用公共后缀表。组织域口径无法确认时保留未知。
3. 按适用策略汇总。DMARC 的 SPF 或 DKIM 任一路通过且对齐，可以支撑通过判定。若有可信接收端 DMARC 结果，同时保留记录值与离线推导值。发布策略、实际收件处置、发送域鉴权和个人发信身份各自引用可支持它的记录。

## 核对

输出每条路径的 `可信来源 / 鉴权结果 / 鉴权域 / From 域 / 对齐模式 / 是否对齐 / 来源行`。抽查折行、多个签名、转发及接收入口变化。现查 DNS 只说明现查时点，历史回算须有对应时点的证据。

## 反例

可信入口记录 `spf=pass smtp.mailfrom=shop.invalid`、`dkim=pass header.d=mailer.invalid`，可见 From 域是 `shop.invalid`。严格模式中只有 SPF 路径通过并对齐。按该口径可支持 DMARC 通过，个人身份与最终投递处置仍各需独立证据。

## 来源

Field 自有方法。依据仓库自有复核 `evidence/next/layered-20261119/candidate-1.1.16/followup-user-tasks/R36/attempt-01/trial/result/report.md`。字段及判断语义来自 [RFC 8601](https://www.rfc-editor.org/rfc/rfc8601)、[RFC 7208](https://www.rfc-editor.org/rfc/rfc7208)、[RFC 6376](https://www.rfc-editor.org/rfc/rfc6376) 。DMARC 参考 [RFC 9989](https://www.rfc-editor.org/rfc/rfc9989)，历史规则参考 [RFC 7489](https://www.rfc-editor.org/rfc/rfc7489)。
