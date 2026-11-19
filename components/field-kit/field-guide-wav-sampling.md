# WAV 采样记录核查

## 输入

取实际 WAV、同次采集的说明或设备记录、问题要求的单位和时间范围。记录摘要、字节数和版本。若要判断声道含义、采集中心频率、起始时刻或校准，需要能绑定到该文件的采集记录。

## 判读

1. 对支持的 PCM WAV，用 `field_observe` 读取 `channels`、`sample_bytes`、`rate_hz`、`frames`，记录解析错误或读不到完整 PCM 的情况。按 RIFF chunk 定位 `fmt ` 和 `data`，处理其他 chunk 和奇数字节填充。只用数据段声明及实际字节交叉验证，完整文件可能含额外元数据。遇扩展、压缩格式或不一致的块结构，用相应格式解释并明示范围。
2. 对固定宽度 PCM，帧字节数为 `channels × sample_bytes`。与数据段字节数做整除与余数核查。时长为 `frames / rate_hz`，每声道标量样本数为 `frames`，全部标量样本数为 `frames × channels`。率和时长保留单位及舍入口径。
3. 同次采集说明明确每帧是同一时刻的一组 I/Q 时，每帧计一个复样本。只有双声道结构时记录帧数和两个声道，I/Q 映射、中心频率和采集起点均按各自来源填写。

## 核对

用帧数、采样率与数据段字节数互相反算，并确认填充字节不计样本。读回所交付的帧、样本与时长字段，避免把 kHz 与 Hz、ms 与 s 混写。比较两次记录时同时核对采样率、声道定义、有效段和单位。

## 反例

双声道 16 位 PCM 含 640 数据字节、采样率 8000 帧/秒，对应 160 帧和 20 ms。说明明确左 I、右 Q 时报告 160 个复样本。只有 WAV 时可报告 320 个声道标量样本，中心频率和 I/Q 用途仍待证。

## 来源

Field 自有方法。依据仓库自有复核 `evidence/next/layered-20261119/candidate-1.1.16/followup-user-tasks/R38/attempt-01/trial/result/report.md` 及 `components/field-kit/materials.py` 的 PCM WAV 观察字段。RIFF 块结构参考 [Microsoft RIFF 说明](https://learn.microsoft.com/en-us/windows/win32/xaudio2/resource-interchange-file-format--riff-)。
