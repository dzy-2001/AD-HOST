# AD-HOST 0.5.1 · Qt6 / MVC

PyQt6 + QtAwesome 双通道触发采集上位机，采用统一 Nord Light 样式与 MVC 目录。波形窗口支持拖动、缩放、原始点光标、双光标测量和图片导出。支持采样时间或点数、前后触发比例、手动触发、电压/电流阈值比较、自动重复记录、精确 HEX 保存及触发相对时间波形。

基于 V26 采集协议；0.4.1 已停用版本、设备标识、初始化信息和时钟的固定值检查。VER/FST 仅作诊断，不再因这些字段不同而拒绝连接；仍需设备提供采集所需的 TST 字段与指令。协议中的自动触发是两路阈值 OR，不是边沿或超时强制触发。每次 ARM 只产生一条记录。

**[Qt6 界面与目录说明](docs/QT6_QUICKSTART.md)** · **[V26 使用说明](docs/V26_QUICKSTART.md)** · [协议依据](docs/protocol/V26_协议指令与上位机开发说明.md) · [设计](docs/superpowers/specs/2026-10-13-v26-trigger-host-design.md)

## 运行

便携版完整解压运行 AD-HOST.exe。源码版需要 Python 3.10+（含 Tcl/Tk）：

```console
python -m pip install -r requirements.txt
python run.py
```

连接 → 设置窗口/阈值/比例 → 准备采集 → 手动点击触发或等待自动条件 → 自动读取保存 → 打开最近记录绘图。

电压沿用 `(raw×2/4096−1)×6 V`，电流暂存 ADC 码。V26 两路都是 12 位无符号，先电压后电流，每组 8 个 ASCII HEX 字符。

传输使用独立协议线程和有界写盘队列；GET 中不会插入查询。只有数据长度、ADC 范围、结束标志和写盘均通过才记成功。失败数据保留为 .partial.hex。保留同名 JSON 才能恢复触发位置与采集配置。

## 验证

```console
python -m unittest discover -s tests -v
python tools/v26_simulator.py --port 11235 --mbps 6
```

Windows CI 运行真实 Tk 的 V26 采集/绘图测试并生成便携版。模拟验证不等同于实际 STM32/FPGA 上板验证。

历史 V3 core/gui 和相关测试保留用于回归参考；主入口 run.py 与 python -m ad_host 均进入 Qt6 界面；活动模型位于 src/models，控制器和视图分别位于 src/controllers、src/views。
