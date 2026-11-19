# 云与 Kubernetes 配置漂移

## 输入

取得期望配置与同环境的观测快照，记录环境、账户或集群、命名空间、采集时间、API 版本和导出覆盖范围。涉及默认值、控制器或继承策略时，补齐已渲染配置、观测快照的 `spec`/`status`、生效规则或变更记录。

## 判读

1. 按 `(环境, API 组/资源类型, 命名空间, 对象名)` 配对，集群级对象单列。涉及同名重建或对象演进时核对 UID、版本转换与采集时点。容器或角色条目按声明的键连接，重名和缺项各自记录。
2. 每个字段列 `期望值 / 快照 spec / 快照 status / 结论`。先统一标量类型和单位。CPU 可统一换算为毫核，内存可统一换算为字节。只有字段语义允许时才归一化顺序或应用缺省值。区分明确的空值、零、未返回和文档规定的缺省语义。
3. 配额按同一快照、同一资源键使用 `status.hard - status.used` 计算，保留原值。任一缺失时剩余额度记 `unknown`。部署分别核对期望与快照 `spec.replicas`，再比较快照 `status.replicas`、`status.availableReplicas` 和期望状态。能取到代次时，按该资源的规则检查 `observedGeneration` 是否已跟上 `generation`。差值只描述该观测点，原因需另有事件或变更证据。

## 核对

从报告随机挑一条，回指前后字段路径并手算差值，优先抽查同名跨命名空间、缺字段及单位等值项。显式标记快照时点和过期状态，登记哪条证据才足以核对运行生效情况。按题意把缺项、真实变化、语义等价分别列出。

## 反例

`3Gi` 与 `3072Mi` 等值。`2G` 与 `2Gi` 差 `147483648` 字节。配额上限明确但快照缺 `status.used.requests.memory` 时，剩余内存为 `unknown`。`spec.replicas=3`、`status.availableReplicas=2` 支持当次快照的差距为 1。

## 来源

Field 自有方法。依据仓库自有复核 `evidence/next/layered-20261119/candidate-1.1.16/domain-round-b/R23/RESULT.md` 的配额与部署字段核对。数量语义参考 [Kubernetes Quantity 说明](https://kubernetes.io/docs/reference/kubernetes-api/common-definitions/quantity/)。
