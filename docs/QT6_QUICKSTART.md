# AD-HOST 0.5.2 · Qt6 / MVC

完整解压便携包，运行 AD-HOST.exe。窗口右上显示连接状态，顶部设置 IP、端口和保存目录；采集、记录、诊断分别位于三个页签。

采集流程与 0.4.1 相同：连接 → 设置记录窗口及触发 → 准备采集 → 手动触发或等待阈值 → 自动保存。版本号、设备标识和时钟固定值检查仍停用。详细协议操作见 V26_QUICKSTART.md。

## 采集设置与光标读数

采样窗口按“设置方式 / 每通道采样时间或点数 / 触发前占比”分列显示。输入框直接显示 ms、点、% 单位，旁边显示触发后占比；下方摘要显示实际点数、时长、文件大小以及触发前后点数。阈值条件每通道一行，对齐显示通道、比较关系、ADC 阈值和说明；电压阈值同时显示按既定公式换算的 V 值。手动触发模式下，下方阈值不参与触发判断。

波形底部为固定读数表：鼠标位置、光标 A、光标 B、差值 B−A 各一行，按采样点、时间 ms、电压 V、电流 ADC 分列；A/B 颜色与曲线标记一致。差值保留正负号，未设置的光标显示“—”，切换或清除记录会清空读数。

采集操作按钮固定在页签底部；窗口较小时可滚动参数区，操作按钮仍可见。

## 波形查看

- 在“记录与波形”打开已完成的 HEX，或选择最近记录。HEX 和同名 JSON 一起保存可恢复触发时间。
- **拖动**：在曲线区域按住左键平移；两通道时间轴联动。
- **滚轮**：以鼠标位置为中心放大/缩小时间轴；**框选放大**可直接选择区域。
- **全貌**：恢复整个记录和纵轴范围；**触发位置**：回到以触发为中心的时间窗口。有元数据才提供触发位置。
- **纵轴适应**：按当前可见数据调整纵轴；也可以输入采样点范围，终点不包含在内。
- 移动鼠标显示最近原始采样点的时间、电压 V、电流 ADC 计数。
- **双光标**：切换测量模式，选择 A/B 后点击曲线；按住已有标记可拖动。读数显示 B−A 的时间差、点数差、电压差及电流计数差。
- **保存图片**：导出当前视图和可见测量标记为 PNG。

大范围曲线为保留峰谷的概览，放大后重新从原始数据生成。光标读原始样本，不读抽稀曲线。100 MHz 对应每点 10 ns；电流没有标定系数，不显示 A。

解析在后台运行，可取消；窗口关闭时取消任务并释放数据。软件退出时先停止 TCP 接收并等待文件关闭。超大文件仍沿用原有 1 GiB ASCII 输入上限。

## 目录结构

```text
src/
  app.py                    应用组装与入口
  models/                   协议、TCP 会话、写盘、文件解析、原始样本计算
  controllers/              采集操作、异步波形任务、交互调度
  views/                    主窗口、波形窗口
    widgets/styles.py       用户提供的通用 GLOBAL_STYLE（保留原文）
    widgets/theme.py        本项目样式补充与 QtAwesome 图标
    widgets/controls.py     通用按钮、卡片、输入控件
ad_host/                    旧模块导入兼容及历史 Tk 界面参考
tests/                      模型与生命周期测试
tools/qt_smoke.py            Qt 采集/绘图/交互测试
```

Model 不依赖 Qt。View 不操作 socket 或读取数据文件。Controller 通过既有后台会话和波形工作线程组织任务，Qt/Matplotlib 只在主线程更新。UI 以 100 ms 周期读取采集快照；波形缩放请求延迟合并并仅保留最新任务，避免排队积累。

## 样式与依赖

前端使用 PyQt6 6.9.1、QtAwesome 1.4.0，图形使用 Matplotlib 的 Qt 画布；保留 NumPy/Matplotlib 版本。样式来源为用户的 Nord Light styles.py，未改动原文件；通用控件外观完全遵循 GLOBAL_STYLE。CheckBox 勾选态采用原定纯色填充；ComboBox 和 SpinBox 按原文件隐藏箭头；下拉选中文字及按钮状态也由通用样式和 Qt 基础风格决定。theme.py 不再覆盖这些控件，不再生成勾号或箭头图片，只负责加载样式、提供 QtAwesome 操作图标，并补充原文件未定义的页签、进度条、参数摘要和光标表格样式。通用控件后续如需修改，应统一维护 styles.py。

源码运行：安装 Python 3.10+，执行 `python -m pip install -r requirements.txt`，然后 `python run.py`。不需要启动 Tk 界面。

测试：`python -m unittest discover -s tests -v`；Qt 界面测试：`python tools/qt_smoke.py`。可设置 `AD_HOST_SCREENSHOTS` 指定截图目录。模拟器仍可使用 `python tools/v26_simulator.py`。

资料：[QtAwesome 使用](https://qtawesome.readthedocs.io/en/stable/usage.html)、[Matplotlib Qt 嵌入示例](https://matplotlib.org/stable/gallery/user_interfaces/embedding_in_qt_sgskip.html)。软件测试与模拟器不能代替实际板卡联调。
