EnREAD/
├── audio/                      # 音频文件保存目录（运行时生成）
├── tasks/                      # 任务记录目录
│
├── main.py                     # 后台主程序入口（鼠标监听、流程控制）
├── floating_ui.py              # 悬浮球主窗口模块
├── list_panel.py               # 录音列表面板模块
├── review_window.py            # 单词复习窗口模块（Leitner盒子系统）
├── word_game.py                # 单词拼句游戏模块
│
├── audio_player.py             # 音频播放控制器模块
├── audio_processor.py          # 音频处理模块（FFmpeg变速）
├── audio_recorder.py           # 音频录制模块（WASAPI Loopback）
│
├── db_manager.py               # 数据库管理模块
├── config_loader.py            # 配置加载模块
├── clipboard_manager.py        # 剪贴板管理模块
├── text_processor.py           # 文本处理模块
├── ui_services.py              # UI服务模块（Socket通信、一致性检查）
├── widgets.py                  # 通用UI组件模块
├── style_manager.py            # 样式管理模块
│
├── alt_trigger.py              # Alt键触发监听模块
├── ctrl_trigger.py             # Ctrl长按触发监听模块（OCR识别）
├── auto_record_trigger.py      # 自动补录触发模块
├── ui_automation.py            # UI自动化模块（获取光标文本）
│
├── config.ini                  # 配置文件
├── data.db                     # SQLite数据库文件（运行时生成）
├── review_window.qss           # 复习窗口QSS样式表
├── requirements.txt            # Python依赖库清单
├── start_app.bat               # 启动脚本
└── test_review.py              # 复习功能测试脚本
flowchart TD
    subgraph 用户操作
        A[拖拽选文 / 双击选文]
    end

    subgraph 后台进程 main.py
        B[MainApp: 鼠标监听]
        C[处理触发逻辑]
        D[UI Automation: 获取选中文本]
        G[TextProcessor: 校验与清洗]
        H{校验结果}
        I[Socket: STOP_PLAYBACK]
        J[AudioRecorder 线程启动]
        K[WASAPI Loopback 监听]
        L{声音 > 阈值?}
        M[开始录制]
        N{静音 > 设定值?}
        O[停止录制]
        P[音频处理: 归一化、填充静音]
        Q[保存 .wav 文件]
        R[FFmpeg: 生成慢速版本]
        S[Database: 插入/更新记录]
        T[Socket: UPDATE:number]
    end

    subgraph UI进程 floating_ui.py
        U[接收 Socket 消息]
        V[刷新列表]
        W{Auto 开启?}
        X[自动播放最新录音]
    end

    A --> B
    B --> C
    C --> D
    D --> G
    G --> H
    H -->|校验失败| Z[结束流程]
    H -->|校验通过| I
    I --> J
    J --> K
    K --> L
    L -->|等待中| K
    L -->|检测到声音| M
    M --> N
    N -->|否| M
    N -->|是| O
    O --> P
    P --> Q
    Q --> R
    R --> S
    S --> T
    T --> U
    U --> V
    V --> W
    W -->|是| X
    W -->|否| Z2[结束]
pip install -r requirements.txt
# 静音检测核心逻辑
rms = np.sqrt(np.mean(data**2))
db = 20 * np.log10(rms + 1e-9)
if db > silence_threshold_db:
    # 检测到声音
# Rubberband 滤镜（高质量）
cmd = [ffmpeg_cmd, '-y', '-v', 'error', '-i', input_path,
       '-af', f'rubberband=tempo={speed}', output_path]

# Atempo 滤镜（回退方案）
cmd = [ffmpeg_cmd, '-y', '-v', 'error', '-i', input_path,
       '-af', f'atempo={speed}', output_path]
# 核心原理
text_pattern = element.GetCurrentPattern(UIA_TextPatternId)
selection = text_pattern.GetSelection()
text = selection.GetElement(0).GetText(-1)
pip install -r requirements.txt
# 方式一：使用启动脚本
start_app.bat

# 方式二：分别启动
python main.py        # 后台进程
python floating_ui.py # UI进程