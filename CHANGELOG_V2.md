# 0.2.0 修改说明

基于用户提供的 AD-Host 工程修改：

- 增加 STM32/FPGA `SET <ms>,1` + `GET` 自动采集流程。
- 按 `800,000 ASCII HEX Byte / ms` 自动计算期望长度。
- SET 成功回复不写入 ADC 文件。
- GET 最终 `\r\n*` 不写入 ADC 文件。
- 只把 ADC HEX 保存为 `capture_*.hex`。
- 自动校验 GET 数据只能包含 `0-9/A-F`。
- 只有“长度完全正确 + 最终 * 正确”才标记 complete=true。
- 显示 GET 进度、GET 实时速度、预计剩余时间、写盘积压。
- 自动 GET 期间禁止发送其他命令，避免协议流污染。
- 增加 FINIT/FST/VER 快捷按钮。
- 增加每次采集独立 JSON 元数据。
- 增加本机 STM32 协议模拟器和 HEX→BIN 转换工具。
- 保留 256 KiB recv、4 MiB SO_RCVBUF、独立写盘线程，不在接收线程实时画波形。
