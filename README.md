# AD-HOST STM32/FPGA 采集与离线绘图 0.3.0

针对当前 STM32F429 + FPGA 采集协议定制的 Windows/Python 上位机。

新增主界面右上角 **解析 HEX / 绘图**：打开已记录的 `.hex` 文件，按电压和电流各两个字节解析，分别绘制电压（V）和电流原始值，横轴按每通道 100 MHz 显示时间。详见 [离线绘图说明](docs/OFFLINE_PLOTTING.md)。

核心目标：**不要再把 SET/VER/FST 回复混进 ADC 数据文件；自动按照采集时间计算 GET 应收长度，并明确判断完整/不完整。**

## 当前协议

自动采集按钮执行：

```text
SET <时间ms>,1\r
等待 \r\n*
GET\r
接收固定长度 ASCII HEX
等待最终 \r\n*
```

当前采样格式按项目约定计算：

```text
1 ms 原始 ADC 数据 = 400,000 Byte
普通 GET 使用 ASCII HEX = 800,000 Byte / ms
```

因此：

| 时间 | GET 应收 ASCII HEX |
|---:|---:|
| 1 ms | 800,000 Byte |
| 10 ms | 8,000,000 Byte |
| 100 ms | 80,000,000 Byte |
| 200 ms | 160,000,000 Byte |

只有同时满足下面两项，才标记为完整：

1. 收满 `时间ms × 800000` 个 HEX 字节；
2. 紧接着收到 `\r\n*`。

如果 TCP 断开、收到 `?`、HEX 数据中出现非 `0-9/A-F` 字节、或收满后结束标记不正确，本次文件会标记 `complete=false`。

## 运行

Python 3.10+：

```console
python -m pip install -r requirements.txt
python run.py
```

Windows 也可双击：

```text
start.bat
```

采集界面使用 Tkinter；离线绘图需要 NumPy 和 Matplotlib，已列入 requirements.txt。Windows 打包版包含依赖，完整解压后直接运行 AD-HOST.exe。

默认设备地址已按当前联调环境填写为：

```text
192.168.3.178 : 11235
```

可在界面修改。

## 推荐使用流程

1. 连接 STM32。
2. 首次联调可点 `FINIT`，确认回复 `*`。
3. 输入采集时间，例如 `10` ms。
4. 点击 **SET + GET 开始采集**。
5. 软件自动等待 SET 成功，再自动 GET。
6. 查看进度、当前速度、预计剩余时间。
7. 完成后查看最新设备回复为 `GET 完成 *`。

自动采集期间会禁用其他命令，避免 `FST/VER/?/*` 插进 GET 数据流。

## 保存文件

每次 TCP 连接创建一个目录，例如：

```text
20261009_170000_ab12cd34/
  session.json
  capture_001_10ms_20261009_170005.hex
  capture_001_10ms_20261009_170005.hex.json
```

`capture_*.hex` **只包含 GET 的 ADC ASCII HEX 数据**，不包含：

- SET 回复；
- FINIT/VER/FST 回复；
- 最后的 `\r\n*`；
- GUI 自己添加的字符。

10 ms 正常文件大小必须正好是：

```text
8,000,000 Byte
```

对应的 JSON 会记录：

```text
capture_ms
expected_hex_bytes
received_hex_bytes
written_hex_bytes
complete
error
elapsed_seconds
```

## 为什么这个版本更适合测速

Socket 接收线程只做：

```text
recv()
→ 协议分流
→ ADC 数据放入写盘队列
→ 马上继续 recv()
```

不会把几 MB HEX 数据实时追加到文本框，也不会边接收边做波形计算。

界面每 200 ms 更新一次；速度约每秒采样一次。磁盘写入由独立线程完成。若待写入缓冲持续接近上限，才说明磁盘写入开始成为瓶颈。

## 本机协议模拟

先运行：

```console
python tools/stm32_protocol_simulator.py --port 11235 --mbps 5
```

然后上位机连接：

```text
127.0.0.1 : 11235
```

输入 `1` ms，点击自动采集。应生成正好 800,000 Byte 的 `.hex` 文件并标记完整。

## HEX 转二进制

如需把 ASCII HEX 压缩回真正字节：

```console
python tools/hex_to_bin.py capture_001_10ms_xxx.hex
```

10 ms 的 8,000,000 Byte HEX 文件会转换成 4,000,000 Byte 二进制文件。

## 测试

```console
python -m unittest discover -s tests -v
```

## 注意

当前自动采集只针对已经确认的普通 `GET` ASCII HEX 协议。没有启用之前尝试过的 GETB 二进制模式。


V3 TEST: 增大TCP接收缓存和写盘队列，用于排查大数据GET卡顿问题。

