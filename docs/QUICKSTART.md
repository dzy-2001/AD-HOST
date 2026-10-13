# 快速开始

## 1. 启动

Windows 双击 `start.bat`，或执行：

```console
python -m pip install -r requirements.txt
python run.py
```

## 2. 连接

默认：

```text
IP   192.168.3.178
Port 11235
```

点击“连接”。状态显示“已连接”后可以操作。

## 3. 自动采集

在“采集时间 ms”输入 1–200，例如 10，然后点击：

```text
SET + GET 开始采集
```

软件会自动：

```text
SET 10,1\r
→ 等待 \r\n*
→ GET\r
→ 接收 8,000,000 Byte HEX
→ 检查最终 \r\n*
```

采集期间不要另发命令；界面也会自动禁用发送按钮。

## 4. 判断是否完整

10 ms 正常：

```text
期望 = 8.000 MB
进度 = 100.00 %
GET 完成 *
```

文件：

```text
capture_xxx_10ms_xxx.hex = 8,000,000 Byte
```

旁边 JSON：

```json
"complete": true
```

如果不完整，JSON 会保存实际 received/written 字节数和 error。

## 5. 看速度

重点看：

- `TCP 当前速度`：整个 Socket 实际收到的速度；
- `GET 当前速度`：本次 ADC HEX 的速度；
- `待写入 / 缓冲`：如果长期接近容量，才说明电脑写盘跟不上；
- `预计剩余`：根据当前 GET 接收速度估算。

## 6. 调试命令

空闲时可直接点：

```text
FINIT
FST
VER
```

回复显示在“最新设备回复”和事件框中，不会写进 ADC `.hex` 文件。

## 7. 离线解析与绘图

点击主界面右上角 **解析 HEX / 绘图**，选择已经记录完成的 `capture_*.hex`。
格式为每组 8 个 ASCII HEX 字符：大端无符号电压 2 字节 + 电流 2 字节。
上图电压按 `(ADC × 2 / 4096 − 1) × 6` 换算为 V，下图电流暂时显示原始值。
每通道采样率 100 MHz，横轴单位 ms。工具栏可缩放、平移和保存图片；也可输入采样点范围查看细节。
详细限制和示例见 [离线绘图说明](OFFLINE_PLOTTING.md)。
