# -*- coding: utf-8 -*-
"""全局样式表 —— Nord Light 专业浅色版"""

# =================================================================
# Nord 色卡常量定义 (Snow Storm & Frost)
# =================================================================
# 极地暗夜 (用于文字和深色强调)
NORD0 = "#2E3440"  # 核心文字色 (黑灰色)
NORD3 = "#4C566A"  # 辅助文字/次要边框色

# 雪暴 (用于背景和基底)
NORD4 = "#D8DEE9"  # 基础边框/深层背景隔离色
NORD4_DARK = "#C4CAD6" # 比NORD4略深的灰色，用于普通按钮边框和按下时的反馈
NORD5 = "#E5E9F0"  # 二级容器/组件背景 (微灰)
NORD6 = "#ECEFF4"  # 窗口主背景 (极其接近白色)

# 冰霜 (蓝色系，对应公司 Logo 调性，用于主视觉)
NORD7 = "#8FBCBB"  # 蓝绿色 
NORD8 = "#88C0D0"  # 浅蓝色 (用于高亮、聚焦状态、选中背景)
NORD9 = "#81A1C1"  # 中蓝色 (用于悬浮交互反馈)
NORD10 = "#5E81AC" # 深蓝色 (主色调，用于核心按钮、标题、主干图标)

# 极光 (功能状态色)
NORD11 = "#BF616A" # 红色 (Danger - 错误、删除、停止)
NORD12 = "#D08770" # 橙色 (特殊警告色)
NORD13 = "#EBCB8B" # 黄色 (Warning - 暂停、警告)
NORD14 = "#A3BE8C" # 绿色 (Success - 运行、启动、正常)

# =================================================================
# 集中式 QSS 样式字典
# =================================================================
GLOBAL_STYLE = f"""
/* ===== 1. 全局基础 ===== */
QMainWindow {{
    background-color: {NORD6}; /* 整个大窗口的最底层颜色 */
}}
QWidget {{
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 10pt;
    color: {NORD0}; /* 统一收口全局字体与默认文字颜色 */
}}

/* ===== 2. 卡片式容器 (替代原生简陋的 QGroupBox) ===== */
QFrame[cssClass="card"] {{
    background-color: {NORD5};
    border: 1px solid {NORD4};
    border-radius: 6px; /* 柔和圆角 */
}}

/* 卡片顶部标题文字专用样式 */
QLabel[cssClass="card-title"] {{
    font-size: 10pt;
    font-weight: bold;
    color: {NORD10};
    border: none;
    background: transparent;
}}

/* ===== 3. 通用基础按钮 ===== */
QPushButton {{
    background-color: {NORD4};
    color: {NORD0};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 9pt;
    font-weight: normal; 
    min-height: 24px;
}}
/* 鼠标悬停态 */
QPushButton:hover {{
    background-color: {NORD5};
    border: 1px solid {NORD9};
}}
/* 鼠标按下态：利用 padding-top 制造按下的物理阻尼感 */
QPushButton:pressed {{
    background-color: {NORD4_DARK}; 
    color: {NORD0};
    border: 1px solid {NORD4_DARK};
    padding-top: 5px;  
    padding-bottom: 3px; 
}}

/* ===== 3.1 语义化按钮：主色 (Primary) ===== */
QPushButton[cssClass="primary"] {{
    background-color: {NORD8};
    color: {NORD0};
    font-weight: normal;
}}
QPushButton[cssClass="primary"]:hover {{
    background-color: {NORD9};
    color: white; /* 悬浮时字体反白加强对比 */
    border: 1px solid {NORD10};
}}
QPushButton[cssClass="primary"]:pressed {{
    background-color: {NORD10};
    color: white;
    border: 1px solid {NORD10};
    padding-top: 5px;
    padding-bottom: 3px;
}}

/* ===== 3.2 语义化按钮：危险 (Danger) ===== */
QPushButton[cssClass="danger"] {{
    background-color: {NORD11};
    color: white;
    font-weight: normal;
}}
QPushButton[cssClass="danger"]:hover {{
    background-color: #D08770; /* 借用 Nord 的偏亮橙红色 */
    border: 1px solid #BF616A;
}}
QPushButton[cssClass="danger"]:pressed {{
    background-color: #A34A54; /* 手动加深的红 */
    border: 1px solid #A34A54;
    padding-top: 5px;
    padding-bottom: 3px;
}}

/* ===== 3.3 语义化按钮：警告 (Warning) ===== */
QPushButton[cssClass="warning"] {{
    background-color: {NORD13};
    color: {NORD0};
    font-weight: normal;
}}
QPushButton[cssClass="warning"]:hover {{
    background-color: #E2C078;
    border: 1px solid #D0B070;
}}
QPushButton[cssClass="warning"]:pressed {{
    background-color: #D0B070;
    border: 1px solid #D0B070;
    padding-top: 5px;
    padding-bottom: 3px;
}}

/* ===== 3.4 语义化按钮：成功 (Success) ===== */
QPushButton[cssClass="success"] {{
    background-color: {NORD14};
    color: {NORD0};
    font-weight: normal;
}}
QPushButton[cssClass="success"]:hover {{
    background-color: #B4D19E;
    border: 1px solid #A3BE8C;
}}
QPushButton[cssClass="success"]:pressed {{
    background-color: #8AA673;
    border: 1px solid #8AA673;
    padding-top: 5px;
    padding-bottom: 3px;
}}

/* ===== 3.5 图形化按钮 ===== */
QPushButton[cssClass="icon"] {{
    background: transparent;
    border: none;
    padding: 0px;
}}
QPushButton[cssClass="icon"]:hover {{
    background: transparent;
}}
QPushButton[cssClass="icon"]:pressed {{
    padding-top: 3px;   /* 按下时图标向下偏移 */
    padding-left: 3px;  /* 按下时图标向右偏移 */
}}
QPushButton::menu-indicator {{
    image: none;        /* 彻底去除下拉倒三角 */
    width: 0px;
}}

/* ===== 4. 计数调节器 (QSpinBox / QDoubleSpinBox，二者完全一致) ===== */
QSpinBox, QDoubleSpinBox {{
    background-color: white;
    border: 1px solid {NORD4};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 22px;
    selection-background-color: {NORD8};
    color: {NORD0};
}}
QSpinBox:hover, QDoubleSpinBox:hover {{ border: 1px solid {NORD9}; }}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {NORD8};
    background-color: {NORD6};
}}
/* 上下按键改造：替换为圆润的灰色块，取消原生三角箭头 */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {NORD4};
    width: 20px;
    border-radius: 4px;
    margin: 2px; /* 留出边距显出立体感 */
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {NORD3}; /* 悬浮时加深反馈 */
}}
QSpinBox::up-arrow, QSpinBox::down-arrow,
QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {{
    image: none; /* 彻底移除系统箭头 */
}}

/* ===== 5. 下拉选择框 (QComboBox) ===== */
QComboBox {{
    background-color: white;
    border: 1px solid {NORD4};
    border-radius: 6px;
    padding: 5px 12px;
    min-height: 22px;
    color: {NORD0};
}}
QComboBox:hover {{ border: 1px solid {NORD9}; }}
QComboBox:focus {{ border: 2px solid {NORD8}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid {NORD5};
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}}
QComboBox::down-arrow {{
    width: 0px; 
    height: 0px; 
    border: none; /* 移除系统默认下拉三角 */
}}
/* 下拉弹出的菜单列表 */
QComboBox QAbstractItemView {{
    background-color: white;
    border: 1px solid {NORD4};
    border-radius: 6px;
    outline: none;
    padding: 4px;
    selection-background-color: {NORD8};
    selection-color: {NORD8};
}}
QComboBox QAbstractItemView::item {{
    min-height: 28px;
    border-radius: 4px;
    padding-left: 8px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {NORD6};
}}

/* ===== 6. 文本输入框 (QLineEdit) ===== */
QLineEdit {{
    background-color: white;
    border: 1px solid {NORD4};
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 22px;
    color: {NORD0};
    selection-background-color: {NORD8}; 
}}
QLineEdit:hover {{ border: 1px solid #B0B8C6; }}
QLineEdit:focus {{
    border: 2px solid {NORD8}; 
    padding: 5px 9px; /* [核心细节] 边框由1px变2px时减小1px的padding，防止框内文字发生抖动偏移 */
}}

/* ===== 7. 多行文本/日志区 (QTextEdit) ===== */
QTextEdit {{
    background-color: #F8FAFB;
    border: 1px solid {NORD4};
    border-radius: 6px;
    padding: 4px;
    color: {NORD0};
    /* 严格区分中英文等宽字体，保证十六进制/报文在换行时绝对对齐 */
    font-family: "Cascadia Code", "Consolas", monospace; 
    font-size: 10pt;
    selection-background-color: {NORD8};
}}
QTextEdit:focus {{
    border: 2px solid {NORD8};
    background-color: white;
}}

/* ===== 8. 滚动条 (QScrollBar 统一美化) ===== */
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0px; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0px; }}

/* 默认滑块颜色与圆润形状 */
QScrollBar::handle:vertical {{ background: {NORD4}; min-height: 30px; border-radius: 4px; }}
QScrollBar::handle:horizontal {{ background: {NORD4}; min-width: 30px; border-radius: 4px; }}

/* 鼠标放上滑块时变深蓝 */
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {NORD9}; }}
/* 按下时的颜色最深 */
QScrollBar::handle:vertical:pressed, QScrollBar::handle:horizontal:pressed {{ background: {NORD10}; }}

/* 彻底隐藏上下/左右两端的默认按钮 */
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; background: none; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; background: none; }}

/* 点击空白翻页区域背景保持透明，不显示突兀色块 */
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

/* ===== 9. 独立标签 (QLabel) ===== */
QLabel {{ 
    color: {NORD0};
    font-size: 10pt;
}}

QLabel[cssClass="title"] {{
    font-size: 11pt;
    font-weight: bold;
    color: {NORD10}; /* 标题使用深蓝强调 */
}}
QLabel[cssClass="content"] {{
    font-size: 10pt;
    font-weight: bold;
    color: {NORD3}; /* 次要内容使用灰蓝色 */
}}

/* ===== 10. 复选框 (QCheckBox) ===== */
QCheckBox {{
    color: {NORD0};
    spacing: 8px;
}}
/* 方框体美化 */
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {NORD9};
    border-radius: 4px;
    background-color: white;
}}
QCheckBox::indicator:hover {{ border: 1px solid {NORD8}; }}
/* 勾选后的纯色填充效果 (勾号通常由图片提供，这里清空原生防止重影) */
QCheckBox::indicator:checked {{
    background-color: {NORD8};
    border: 1px solid {NORD8};
    image: none; 
}}
"""
