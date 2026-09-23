# Bocpaste — 截图 & 贴图工具

对标 [Snipaste 2.11.3](https://www.snipaste.com/) 开发的 Windows 截图软件，使用 **Python 3.12 + PySide6 (Qt6)** 实现，界面交互、配色与操作习惯尽量与 Snipaste 保持一致。

## 功能一览

### 截图
- **区域截图**：按住左键拖拽框选任意区域
- **智能窗口识别**：自动检测鼠标下的顶层窗口；可深入识别**子控件**（按钮、输入框、面板等）
  - `Tab` / `Shift+Tab` 在「控件 → 父窗口 → 主窗口」之间循环切换
- **放大镜**：实时显示放大像素、像素网格、**屏幕坐标**与 **RGB 颜色值**（倍数可配）
- 选区遮罩、选区边框颜色/浓度可自定义
- 选区可**移动、八向缩放**（手柄拖拽），方向键微调（`Shift` 加速 ×10）
- `Ctrl+A` 快速选中当前显示器
- 双击选区 = 复制并退出

### 标注（截图工具栏）
| 工具 | 快捷键 |
|---|---|
| 矩形框（按住 Shift 为正方形） | `1` |
| 椭圆（按住 Shift 为正圆） | `2` |
| 箭头（按住 Shift 锁定 45°） | `3` |
| 直线（按住 Shift 锁定 45°） | `4` |
| 画笔 | `5` |
| 马克笔（半透明宽头） | `6` |
| 文字（就地多行输入，Enter 确认） | `7` |
| 马赛克 | `8` |
| 模糊 | `B` |
| 序号（自动递增） | `9` |
| 橡皮擦 | `0` |

- 16 色预设调色板 + 自定义颜色，笔宽 1–30 可调
- `Ctrl+Z` / `Ctrl+Y` 撤销重做

### 输出
- `Enter` 或双击：**复制到剪贴板**并退出
- `Ctrl+S`：保存为 PNG / JPG / BMP
- `Ctrl+D`：**钉到屏幕**（贴图）
- `Esc`：取消

### 贴图（钉屏）
- 无边框置顶，原位显示，可拖到任意位置（**边缘自动吸附**）
- 滚轮缩放（以光标为中心）；`Ctrl+滚轮` 调整不透明度
- 右键菜单：缩放档位、不透明度、左右旋转、水平/垂直翻转、暂停 GIF、鼠标穿透、复制、保存、重置、关闭
- 双击切换**鼠标穿透**（穿透后点击不影响贴图）；`Shift+双击` 取消穿透
- 支持 **GIF 动图**（剪贴板复制 GIF 文件后贴图）
- 托盘菜单可显示/隐藏所有贴图、取消所有鼠标穿透

### 其他
- 全局热键（低级键盘钩子，支持单键如 F1、PrintScreen）
- 系统托盘常驻（左键托盘图标快速截图）
- 历史截图（托盘菜单中重新贴图，数量可配）
- 首选项：开机自启、热键自定义、截图外观、贴图行为
- 单实例运行、Per-Monitor V2 DPI 感知（高分屏/多屏不发虚）
- 便携化：配置保存在程序目录的 `config.ini`

## 默认热键

| 功能 | 热键 |
|---|---|
| 截图 | `F1` |
| 将剪贴板内容贴图 | `Ctrl+F1` |
| 显示/隐藏所有贴图 | `Ctrl+Shift+`` ` |

## 运行环境

- Windows 10 / 11
- Python 3.10+（开发环境 3.12）
- 依赖：仅 `PySide6`

```bat
pip install PySide6
```

## 移植到其他电脑

### 方式 A：独立 exe（推荐，目标电脑无需安装 Python）

1. 在本机构建（已安装 PyInstaller）：
   ```bat
   py -3.12 -m PyInstaller --noconfirm --clean --onefile --noconsole ^
       --icon=icon.ico --name Bocpaste main.py
   ```
2. 把 `dist\Bocpaste.exe` 拷到目标电脑任意目录（如 `D:\Bocpaste\`）。
3. 双击运行——配置 `config.ini` 和 `history\` 会自动生成在 exe 同目录（便携式）。
4. 开机自启：托盘菜单 → 首选项 → 常规 → 勾选「开机时自动启动」（写当前用户注册表）。

### 方式 B：源码方式（目标电脑需 Python 3.10+）

1. 拷贝整个 `Bocpaste` 目录（`app\`、`main.py`、`requirements.txt`）。
2. 目标电脑执行 `pip install PySide6`。
3. 运行 `py -3.12 main.py`（或双击 `启动.bat`）。

## 启动方式

```bat
:: 后台驻留（托盘）
启动.bat
:: 或直接
py -3.12 main.py

:: 立即进入截图（可固定到任务栏/创建桌面快捷方式）
截图.bat
py -3.12 main.py snip

:: exe 版
Bocpaste.exe          :: 驻留托盘
Bocpaste.exe snip     :: 立即截图
```

## 项目结构

```
Bocpaste/
├── main.py                 入口（DPI 感知、单实例、命令行参数）
├── 启动.bat / 截图.bat
└── app/
    ├── application.py      顶层控制器：串联各模块
    ├── config.py           便携配置 config.ini
    ├── hotkey_manager.py   全局热键（WH_KEYBOARD_LL 钩子）
    ├── tray.py             系统托盘
    ├── settings_dialog.py  首选项（常规/热键/截图/贴图）
    ├── icons.py            程序化矢量图标（无二进制资源）
    ├── win32.py            Win32 API：DPI 转换、窗口检测、鼠标穿透
    ├── snip/
    │   ├── capture.py      虚拟桌面画面捕获
    │   ├── snipper.py      截图覆盖层（选区/检测/交互状态机）
    │   ├── toolbar.py      标注工具栏
    │   ├── shapes.py       标注图元
    │   ├── magnifier.py    放大镜
    │   └── text_editor.py  就地文字输入
    └── paste/
        ├── paster.py       贴图窗口
        └── paster_manager.py
```

## 与 Snipaste 的差异 / 待完善

- 暂未实现：贴图分组（虚拟桌面）、贴图备份恢复、延迟截图、多屏独立 DPI 混合缩放下的像素级坐标校准
- 无多语言（仅简体中文）；图标为程序化绘制，风格接近但不完全相同
