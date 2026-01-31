# 2026newReadingI

```python
# Project Overview

## 1. 项目文件结构

```

d:Scanner2026newReadingI\

├── styles/                  # QSS 样式文件目录

│   └── review_window.qss    # 复习窗口样式

├── tasks/                   # 任务记录目录

├── audio_[player.py](http://player.py)          # 音频播放控制器模块

├── audio_[processor.py](http://processor.py)       # 音频处理模块 (FFmpeg 变速)

├── audio_[recorder.py](http://recorder.py)        # 音频录制模块 (WASAPI Loopback)

├── clipboard_[manager.py](http://manager.py)     # 剪贴板管理模块

├── config.ini               # 配置文件

├── config_[loader.py](http://loader.py)         # 配置加载模块

├── data.db                  # SQLite 数据库文件

├── db_[manager.py](http://manager.py)            # 数据库管理模块

├── floating_[ui.py](http://ui.py)           # 悬浮球主窗口模块

├── list_[panel.py](http://panel.py)            # 录音列表面板模块

├── [main.py](http://main.py)                  # 后台主程序 (鼠标监听、流程控制)

├── requirements.txt         # 依赖库清单

├── review_[window.py](http://window.py)         # 单词复习窗口模块

├── start_app.bat            # 启动脚本

├── style_[manager.py](http://manager.py)         # 样式管理模块

├── text_[processor.py](http://processor.py)        # 文本处理模块

├── ui_[services.py](http://services.py)           # UI 服务模块 (Socket通信、一致性检查)

├── [widgets.py](http://widgets.py)               # 通用 UI 组件模块

└── word_[game.py](http://game.py)             # 单词拼句游戏模块

```jsx

## 2. 模块职责说明

| 文件名 | 职责描述 |
| :--- | :--- |
| **main.py** | 程序的后台入口。负责全局鼠标监听（拖拽/双击触发），协调剪贴板读取、文本处理和录音流程的启动与停止。 |
| **floating_ui.py** | 悬浮球主窗口。负责初始化数据库、一致性检查，管理悬浮球的显示和交互。 |
| **list_panel.py** | 录音列表面板。包含日期筛选、列表展示、右键菜单，以及 Review 按钮入口。 |
| **audio_player.py** | 音频播放控制器。管理播放队列、播放模式（循环/顺序）和音频输出。 |
| **review_window.py** | 单词复习窗口。实现 Leitner 盒子系统，提供「记得/不记得」交互，支持 QSS 样式热重载。 |
| **word_game.py** | 单词拼句游戏窗口。将句子打乱后让用户重组还原。 |
| **widgets.py** | 通用 UI 组件。包含 Toggle 开关、自定义按钮等可复用组件。 |
| **ui_services.py** | UI 服务模块。包含 Socket 通信服务和启动时的一致性检查器 (`ConsistencyChecker`)。 |
| **audio_recorder.py** | 负责音频录制。使用 WASAPI Loopback 录制系统声音，包含静音检测逻辑，录音保存时自动初始化单词复习字段。 |
| **audio_processor.py** | 音频后处理工具。调用 FFmpeg 生成慢速版本的音频文件（使用 `rubberband` 或 `atempo` 滤镜）。 |
| **db_manager.py** | 数据库抽象层。封装 SQLite 操作，管理录音记录的增删查改，包含 Leitner 盒子系统的查询和更新方法。 |
| **config_loader.py** | 配置管理。负责读取 `config.ini`，提供类型安全的配置项访问属性，包含 Leitner 盒子间隔配置。 |
| **clipboard_manager.py** | 剪贴板操作。负责模拟 Ctrl+C 获取选中文本，并实现了剪贴板内容的备份与恢复机制。 |
| **text_processor.py** | 文本清洗与校验。负责过滤非英文字符，校验文本长度和有效性，包含单词识别函数 `is_valid_word()`。 |
| **style_manager.py** | 样式管理。负责加载 `.qss` 样式文件，支持 F5 热重载。 |

## 3. 核心类与函数清单

### main.py
*   **`MainApp`**: 主应用类。
    *   `on_click(x, y, button, pressed)`: 鼠标点击回调，检测拖拽和双击事件。
    *   `handle_trigger()`: 触发处理流程（停止旧任务，启动新流程）。
    *   `run_process_flow()`: 核心工作流：剪贴板获取 -> 文本校验 -> 停止播放 -> 启动录音。
*   **`ExitServer`**: 监听 socket 端口，接收退出信号以关闭后台进程。

### audio_recorder.py
*   **`AudioRecorder` (Thread)**: 录音线程类。
    *   `get_loopback_mic()`: 获取系统默认扬声器的 Loopback 设备。
    *   `run()`: 执行录音循环，计算 RMS dB 值进行静音检测。
    *   `save_file()`: 录音结束后的处理（归一化、填充静音）和保存。

### audio_processor.py
*   **`generate_slow_audio(input_path, speeds)`**: 调用系统 FFmpeg 生成指定倍速的音频文件。

### floating_ui.py
*   **`FloatingBall` (QWidget)**: 悬浮球主窗口，负责初始化数据库、启动 Socket 服务和一致性检查。
### list_panel.py
*   **`ListPanel` (QWidget)**: 录音列表面板，包含日期筛选、列表展示和 Review 按钮入口。
### audio_player.py
*   **`AudioPlayer` (QObject)**: 音频播放控制器，管理播放队列、播放模式（循环/顺序）和音频输出。
### review_window.py
*   **`ReviewWindow` (QWidget)**: 单词复习窗口。
    *   实现 Leitner 盒子系统，提供「记得/不记得」交互。
    *   支持 QSS 样式热重载 (F5)。
    *   窗口位置记忆。
### word_game.py
*   **`WordGameWindow` (QWidget)**: 单词拼句游戏窗口。
### widgets.py
*   **`ToggleSwitch` (QWidget)**: 自定义 Toggle 开关组件。
*   其他通用 UI 组件。
### ui_services.py
*   **`ConsistencyChecker` (QThread)**: 启动时检查数据库记录与磁盘文件的一致性。
*   **Socket 通信服务**: 处理进程间通信。
### style_manager.py
*   **`StyleManager`**: 样式管理器，负责加载和热重载 QSS 文件。
### text_processor.py
*   **`is_valid_word(text)`**: 判断文本是否为合法英文单词。

### db_manager.py
*   **`DatabaseManager`**:
    *   `insert_recording(...)`: 插入新录音记录。
    *   `get_recordings_by_date(...)`: 按日期查询录音。
    *   `delete_recording(...)`: 删除录音记录。
    *   <span color="red">`migrate_add_review_fields()`: 迁移方法，添加 Leitner 盒子系统所需字段（box_level, next_review_date, last_review_date）。</span>
    *   <span color="red">`get_words_to_review()`: 获取待复习的单词列表（next_review_date <= 今天）。</span>
    *   <span color="red">`update_word_box(...)`: 更新单词的复习状态（box_level, next_review_date, remember, forget, last_review_date）。</span>
    *   <span color="red">`get_review_stats()`: 获取复习统计信息（待复习数量、今日已完成数量）。</span>

## 4. config.ini 配置参数说明

### [Audio] - 录音设置
*   `start_silence_duration`: 开始录音前允许的最大静音时长（秒），超时则放弃。
*   `max_recording_duration`: 最大录音时长（秒）。
*   `silence_threshold_db`: 静音阈值（dB），低于此值视为静音。
*   `end_silence_duration`: 录音过程中，持续静音多少秒后自动停止。

### [Paths] - 路径设置
*   `save_dir`: 音频文件保存目录（默认为 `audio`）。

### [UI] - 界面基础设置
*   `ball_diameter`: 悬浮球直径。
*   `panel_width`: 列表面板宽度。
*   `panel_max_height`: 列表面板最大高度。
*   `opacity`: 窗口透明度。
*   `font_size`: 基础字体大小。
*   `refresh_interval`: 列表自动刷新间隔（毫秒）。
*   `last_position`: 悬浮球上次退出时的位置。

### [PlayMode] - 播放模式
*   `default_mode`: 默认播放模式。
*   `mode2_loop_count`: Mode2 下的单曲循环次数。
*   `auto_enabled`: 是否开启录音完成后自动播放。

### [SlowAudio] - 慢速音频
*   `generate_slow_versions`: 是否生成慢速版本。
*   `slow_speeds`: 需要生成的慢速倍率列表（如 `0.5, 0.75`）。

### [WordGame] - 单词游戏
*   `min_text_length`: 触发游戏功能的最小文本长度。
*   `game_window_width` / `game_window_height`: 游戏窗口尺寸。

### [Database] - 数据库
*   `db_path`: 数据库文件路径。
*   `wal_mode`: 是否开启 WAL 模式（提高并发性能）。

*(注：ReviewWindow, ContextMenu, DateFilter 等节包含具体的 UI 颜色、尺寸和布局配置，在此不一一列举)*

## 5. 程序主要工作流程

```

graph TD

User[用户操作] -->|拖拽选文 / 双击选文| MouseListener[MainApp: 鼠标监听]

MouseListener -->|触发| TriggerHandler[处理触发逻辑]

TriggerHandler -->|1. 备份并清空剪贴板| Clipboard[ClipboardManager]

Clipboard -->|2. 模拟 Ctrl+C| SystemClipboard[系统剪贴板]

SystemClipboard -->|3. 获取文本| Validator[TextProcessor: 校验与清洗]

Validator -->|校验失败| End[结束流程]

Validator -->|校验通过| RecorderInit[初始化录音]

RecorderInit -->|Socket: STOP_PLAYBACK| UI_Player[UI: 停止当前播放]

RecorderInit -->|启动| AudioThread[AudioRecorder 线程]

AudioThread -->|监听系统音频| WASAPI[WASAPI Loopback]

WASAPI -->|等待声音 > 阈值| Recording[开始录制]

Recording -->|静音时长 > 设定值| StopRecording[停止录制]

StopRecording -->|保存| WAVFile[生成 .wav 文件]

WAVFile -->|FFmpeg| SlowGen[生成慢速版本]

WAVFile -->|插入记录| DB[Database: data.db]

DB -->|Socket: UPDATE| UI_Update[UI: 刷新列表]

UI_Update -->|若开启自动播放| AutoPlay[播放最新录音]

Clipboard -->|4. 恢复剪贴板| SystemClipboard

```

## 6. 依赖库清单 (requirements.txt)

*   `pynput`: 用于监听鼠标事件和模拟键盘按键。
*   `pyperclip`: 用于跨平台的剪贴板读写操作。
*   `soundcard`: 用于音频录制（支持 WASAPI Loopback）。
*   `soundfile`: 用于读写 WAV 音频文件。
*   `numpy`: 用于音频数据处理（RMS 计算、归一化、数组拼接）。
*   `pywin32`: 提供了 Windows API 的访问（虽然代码中直接引用较少，可能是 soundcard 或其他库的依赖）。
*   `PyQt6`: 用于构建图形用户界面。

## 7. 技术实现细节

1.  **WASAPI Loopback 录音**:
    *   使用 `soundcard` 库获取默认扬声器的 Loopback 设备，从而录制系统内部发出的声音（如 TTS 发音），而非麦克风声音。
    *   通过计算音频块的 RMS（均方根）并转换为 dB 值来实现基于阈值的静音检测。

2.  **FFmpeg 变速处理**:
    *   调用系统安装的 `ffmpeg` 命令行工具。
    *   优先尝试 `rubberband` 滤镜（音质更好），如果失败则回退到 `atempo` 滤镜。
    *   生成的文件名格式为 `{number}@{speed}.wav`。

3.  **剪贴板无感操作**:
    *   在捕获文本前，先读取当前剪贴板内容并保存。
    *   执行捕获后，延时将原内容写回剪贴板，尽量减少对用户正常复制粘贴操作的干扰。

4.  **双进程架构**:
    *   **后台进程 (`main.py`)**: 负责由于权限或稳定性原因更适合独立运行的输入监听和录音任务。
    *   **UI 进程 (`floating_ui.py`)**: 负责界面展示。
    *   **通信**: 两个进程通过本地 Socket (`127.0.0.1:65432` 和 `65433`) 进行简单的信号通信（如停止播放、刷新列表、退出程序）。

5.  **数据一致性维护**:
    *   UI 启动时会运行 `ConsistencyChecker`，比对数据库记录和磁盘上的 `.wav` 文件。
    *   自动删除没有对应文件的数据库记录，或没有对应数据库记录的孤儿文件，保持数据整洁。

```

## 我的项目的逻辑和功能

```python
根据这份文档，你的项目是一个 **Windows 桌面语言学习辅助工具**，整体功能逻辑如下：

---

## 🎯 核心定位

后台静默监听用户操作，自动抓取选中的英文单词/句子并录制系统发音，配合悬浮窗口实现复习播放。**数据通过 SQLite 数据库统一管理**。

---

## 📦 功能模块

### 1. 录音采集模块

```

触发 → 剪贴板管理 → 校验清洗 → WASAPI录音 → 智能断句 → 数据库写入 → 文件保存

```jsx

- **触发**：监听鼠标双击/拖拽选中文本
- **剪贴板**：备份 → Ctrl+C复制 → 读取 → 恢复原内容
- **校验**：文本格式、≤600字符、去重
- **录音**：6秒静音过滤、最长30秒、1.5秒静音断句
- **保存**：去首尾静音 + 0.3秒缓冲，基于数据库自增 number 生成文件名

### 2. 数据库管理

使用 SQLite 数据库（data.db）存储录音元数据：

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| number | INTEGER | 自增主键，用于文件命名和记录识别 |
| content | TEXT | 录音对应的完整文本内容 |
| remember | INTEGER | 预留字段（记住次数） |
| forget | INTEGER | 预留字段（忘记次数） |
| date | DATE | 录音日期 (YYYY-MM-DD) |
| <span color="red">box_level</span> | <span color="red">INTEGER</span> | <span color="red">Leitner 盒子等级（1-5），默认值 1</span> |
| <span color="red">next_review_date</span> | <span color="red">DATE</span> | <span color="red">下次复习日期</span> |
| <span color="red">last_review_date</span> | <span color="red">DATE</span> | <span color="red">上次复习日期，默认 NULL</span> |

**并发安全策略**：

- 启用 WAL 模式提升读写并发性能
- 设置 busy_timeout 避免死锁
- 写操作失败时自动重试

### 3. 音频文件命名规则

基于数据库 number 字段的纯数字命名：

- 1 倍速文件：`{number}.wav`
- 0.75 倍速文件：`{number}@0.75.wav`
- 0.5 倍速文件：`{number}@0.5.wav`

示例：若 number 为 42，则文件名为 `42.wav`、`42@0.75.wav`、`42@0.5.wav`

### 4. 变速音频生成

录音保存后自动生成变速版本：

- 使用 FFmpeg + Rubberband 滤镜实现时间拉伸（音调不变）
- 若 Rubberband 不可用，回退到 atempo 滤镜

### 5. 悬浮窗口 UI

| 状态 | 形态 |
| --- | --- |
| 默认 | 绿色悬浮球（可拖拽） |
| 悬浮 | 向左上展开为半透明列表面板 |

**列表面板功能**：

- 从数据库查询并显示录音列表（按 number 倒序）
- 显示 content 字段内容（超长时截断加 "..."，tooltip 显示完整内容）
- 播放/暂停控制
- 日期筛选下拉框（从数据库查询，最多15天）
- 右键删除（同步删除数据库记录和三个音频文件）

### 6. 播放模式

| 模式 | 行为 |
| --- | --- |
| Mode1 | 渐进式：0.5x → 0.75x → 1x 各播放一次 |
| Mode2 | 重复式：1x 循环播放 3/5/7 次（可切换） |
| Auto开关 | 录音完成后自动播放 |

### 7. 单词还原句子游戏

- **触发条件**：数据库 content 字段字符数 > 30（判定为句子）
- **数据来源**：通过 number 查询数据库获取 content 内容
- **玩法**：打乱单词顺序 → 用户点击重组 → 验证是否还原正确

### 8. 启动时一致性校验

由 UI 进程执行，确保数据库与文件系统同步：

- 数据库有记录但音频文件不存在 → 删除数据库记录
- 音频文件存在但数据库无记录 → 删除音频文件及变速版本

### 9. 自动清理机制

- 启动后延迟执行（默认60秒）
- 检测有录音的日期数量是否超过限制（默认15个）
- 删除超期日期的所有录音记录和对应音频文件
- 每条记录独立事务处理，单条失败不影响其他清理

### 10. 复习单词界面（设计中）

- 独立悬浮窗口，随机显示近期单词
- "记得"/"不记得"按钮 → 更新数据库 remember/forget 字段
- 根据记忆次数阈值决定是否继续显示

---

## 🔄 数据流

```

选中文本 → 剪贴板复制 → 校验清洗

↓

WASAPI录音系统发音 → 智能断句停止

↓

数据库插入记录(获取number) → 保存 {number}.wav → 生成变速版本

↓

Socket通知UI → UI查询数据库刷新列表 → (Auto开启时) 自动播放

↓

用户通过悬浮窗口复习播放 / 进行句子还原游戏

```

---

## 🔗 进程间通信 (IPC)

程序分为两个独立进程运行：

| Socket | Server | Client | 用途 |
| --- | --- | --- | --- |
| 65432 | UI进程 | 后台进程 | 录音完成通知、停止播放指令 |
| 65433 | 后台进程 | UI进程 | 退出指令 |

Socket 消息仅作为事件通知，所有数据交换通过数据库完成。

---

## ⚙️ 技术栈

- **语言**：Python + PyQt6
- **录音**：soundcard (WASAPI Loopback)
- **变速**：FFmpeg + Rubberband 滤镜
- **数据库**：SQLite (WAL模式)
- **配置**：config.ini 集中管理所有参数

---

这是一个完整的"录制-存储-复习"闭环工具，核心价值是 **无感录制系统发音 + SQLite数据管理 + 多倍速复习播放**。
```