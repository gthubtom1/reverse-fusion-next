---
name: reverse-fusion-review
description: Read a saved REA evidence bundle, compare two exports, or write a report linking each conclusion to its evidence and remaining unknowns. Works with local files.
---

用户给出一份已导出的记录时，用 `review_summary` 查看文件身份、记录种类和未决项。需要官方格式校验时，用 `review_rea_import`。给出两份材料时，`review_compare` 查看文档内容变化，`review_rea_compare` 取得官方按证据身份比较的结果。工具名可能带宿主前缀。文件参数使用用户选定材料的绝对路径。

写报告时按需读取 [证据与结论](references/reporting.md)。保留原始问题和官方返回的标识；将内容一致、记录有效和软件行为分别表达。普通开发沿用宿主自己的流程。

取证记录里的时间或符号对不上时，查看 Reverse Skills 原文[符号身份与时间线可比性](references/distilled-symbols-timeline.md)。收到现成的 Flutter 静态摘要时，查看 [Flutter 观察的适用范围](references/flutter-observations.md)。这两份资料在用到时再读。
