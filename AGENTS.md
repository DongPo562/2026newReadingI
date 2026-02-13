# AGENTS.md - 项目导航图

## 项目概述
Windows英语阅读助手：选词 → 查录音/录录音 → 复习答题。通过系统音频录制TTS朗读，结合UI Automation获取文本，实现一键录音和复习。

## 启动命令
```bash
pip install -r requirements.txt
python main.py          # 后台服务：键盘/鼠标监听 + 触发器
python floating_ui.py   # UI界面：悬浮球 + 列表面板 + 复习窗口
```

---

## 架构分层

### 1. 入口层
| 文件 | 角色 | 说明 |
|------|------|------|
| `main.py` | 后台入口 | 启动所有触发器监听器，管理ExitServer(65433端口) |
| `floating_ui.py` | UI入口 | FloatingBall悬浮球，启动CommandServer(65432端口) |

### 2. 触发层（用户交互入口）
| 文件 | 触发条件 | 流程 |
|------|---------|------|
| `alt_trigger.py` | Alt键释放 | 三击选中 → UIA取词 → letter_sequence查库 → 匹配:发PLAY命令 / 未匹配:调auto_record |
| `ctrl_trigger.py` | Ctrl长按≥1.5s | OCR取词 → 清洗校验 → 查库 → 重复:等声音结束播放 / 新词:AudioRecorder录制 |
| `quiz_trigger.py` | Ctrl+U | UIA取选中词+句子 → 入库review_questions → AIService出题 → subprocess启动quiz_card.py |
| `emoji_trigger.py` | 鼠标中键/Alt+\ | UIA取词 → 校验英文 → AIService生成emoji → 方向键定位+Ctrl+V粘贴 |
| `auto_record_trigger.py` | 被动调用 | OCR找"朗读"按钮 → 点击 → AudioRecorder录制 |

### 3. UI层
```
floating_ui.py (FloatingBall)
    ├── list_panel.py (ListPanel)
    │       ├── ModeSelector: 播放模式切换(mode1/mode2)
    │       ├── DateFilterComboBox: 日期筛选
    │       └── AudioListItem: 录音列表项
    ├── review_window.py (ReviewWindow)
    │       └── Leitner盒子复习(5级间隔)
    └── word_game.py (WordGameWindow)
            └── 句子还原游戏(标点固定/单词打乱)

quiz_card.py (独立进程)
    └── 多题型答题卡(choice/fill/qa)
```

### 4. 服务层
| 文件 | 职责 |
|------|------|
| `ai_service.py` | LLM出题+批改，ThreadPoolExecutor，多模型级联(Kimi/DeepSeek/GLM/Doubao) |
| `audio_recorder.py` | WASAPI Loopback录音，静音检测，归一化，内容去重覆盖 |
| `audio_processor.py` | FFmpeg变速(rubberband优先/atempo兜底)，生成0.5x/0.75x版本 |
| `audio_player.py` | QMediaPlayer播放队列，mode1(多速序列)/mode2(循环N次) |
| `ui_automation.py` | comtypes UIA: get_selected_text + get_text_at_cursor，三级查找(焦点→鼠标→前台窗口) |
| `text_processor.py` | 文本清洗(非ASCII去除)，单词校验(is_valid_word)，letter_sequence提取 |

### 5. 数据层
| 文件 | 职责 |
|------|------|
| `db_manager.py` | SQLite + threading.local线程安全，_execute_with_retry重试机制，自动迁移 |
| `ui_services.py` | CommandServer(socket监听65432)，ConsistencyChecker(启动时DB↔文件对账)，FileCleaner(定时清理) |
| `config_loader.py` | config.ini配置加载，支持热更新 |

### 6. 工具层
| 文件 | 职责 |
|------|------|
| `widgets.py` | ToggleSwitch, ClickableLabel基础组件 |
| `style_manager.py` | QSS样式加载/缓存/热更新 |

---

## 数据流向图

```
                            ┌─────────────────┐
    用户操作 ──触发器──→     │  ui_automation  │ UIA取词
                            └────────┬────────┘
                                     ↓
                            ┌─────────────────┐
                            │ text_processor  │ 清洗+letter_sequence
                            └────────┬────────┘
                                     ↓
         ┌───────────────────────────┼───────────────────────────┐
         ↓                           ↓                           ↓
┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
│   db_manager    │        │ audio_recorder  │        │   ai_service    │
│ letter_seq查库  │        │ WASAPI录音      │        │ LLM出题/批改    │
└────────┬────────┘        └────────┬────────┘        └────────┬────────┘
         │                          │                          │
         ↓                          ↓                          │
┌─────────────────┐        ┌─────────────────┐                │
│  recordings表   │───────→│  audio_player   │                │
│ review_questions│        │  QMediaPlayer   │                │
└────────┬────────┘        └────────┬────────┘                │
         │                          │                          │
         │                          ↓                          ↓
         │                 ┌─────────────────┐        ┌─────────────────┐
         │                 │  floating_ui    │        │   quiz_card.py  │
         │                 │  (socket 65432) │        │  (subprocess)   │
         └────────────────→└─────────────────┘        └─────────────────┘
```

---

## 核心概念

### letter_sequence（字母序列匹配）
- **定义**: 从文本中提取纯英文字母，转小写，用于模糊匹配
- **示例**: "Hello!" → "ehlo", "don't" → "dnot"
- **用途**: 容错匹配（忽略标点、大小写）
- **实现**: `text_processor.extract_letter_sequence()`

### box_level（Leitner盒子系统）
- **定义**: 复习等级(1-5)，控制复习间隔天数
- **间隔**: 1→2→4→7→14天（可在config.ini配置）
- **规则**: 记得→升级，不记得→重置为1
- **实现**: `review_window.py`, `db_manager.update_word_box()`

### socket通信（进程间通信）
- **端口65432**: CommandServer，接收PLAY/STOP_PLAYBACK/UPDATE/SILENT_RECORD_START
- **端口65433**: ExitServer，接收EXIT命令关闭main.py
- **格式**: `PLAY:{number}:{count}` / `UPDATE:{number}`

### 文件命名规则
- 录音文件: `data/recordings/{number}.wav`
- 变速版本: `{number}@0.5.wav`, `{number}@0.75.wav`

---

## 数据库表结构

### recordings表
| 字段 | 类型 | 说明 |
|------|------|------|
| number | INTEGER PK | 自增主键 |
| content | TEXT | 录音文本内容 |
| date | DATE | 录音日期 |
| letter_sequence | TEXT | 字母序列（用于匹配） |
| box_level | INTEGER | Leitner等级(1-5) |
| next_review_date | DATE | 下次复习日期 |
| last_review_date | DATE | 上次复习日期 |
| remember | INTEGER | 记得次数 |
| forget | INTEGER | 忘记次数 |

**索引**: `idx_date`, `idx_letter_sequence`

### review_questions表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| save_time | TEXT | 保存时间 |
| content | TEXT | 知识点内容 |
| sentence_content | TEXT | 原句内容 |
| ai_status | TEXT | pending/success/failed |
| ai_question | TEXT | AI生成的题目(JSON) |
| user_answer | TEXT | 用户答案 |
| is_correct | INTEGER | 是否正确 |
| ai_feedback | TEXT | AI反馈 |
| answered_time | TEXT | 答题时间 |

---

## 关键约束与约定

1. **内容去重**: 相同content的录音会覆盖旧文件，更新date字段
2. **单词判定**: `is_valid_word()` - 仅字母/连字符/撇号，无空格，长度≤35
3. **UI标签清理**: 自动移除"Heading 3"、"Text "等UI前缀
4. **修饰键模拟**: ReviewWindow悬浮单词区时自动按下Ctrl（可配置）
5. **静默录音模式**: auto_record触发时不自动播放（可配置）

---

## 配置文件说明

配置文件: `config.ini`，主要配置节：

- `[Audio]`: 录音参数（静音阈值、最大时长等）
- `[UI]`: 悬浮球尺寸、面板尺寸、颜色等
- `[PlayMode]`: 播放模式(mode1/mode2)、循环次数
- `[AltTrigger]`: Alt触发参数
- `[CtrlTrigger]`: Ctrl长按触发参数
- `[QuizTrigger]`: 出题API配置、模型选择
- `[EmojiTrigger]`: Emoji生成配置
- `[ReviewWindow]`: 复习窗口布局、Leitner间隔

API密钥: 优先从`.env`文件读取`NIM_API_KEY`或`DOUBAO1.8_API_KEY`
