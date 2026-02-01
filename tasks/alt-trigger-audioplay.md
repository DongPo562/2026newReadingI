阶段一：Alt 键匹配与播放

# EnREAD 功能开发：Alt 键触发内容匹配与播放

## 项目背景

你正在为 EnREAD 项目开发新功能。EnREAD 是一个 Windows 桌面应用，用于英语阅读辅助，使用 Python 3.x + PyQt6 + SQLite + Socket IPC + pynput 技术栈。

现有架构中，main.py 是后台进程入口，floating_ui.py 是 UI 进程入口，db_manager.py 封装数据库操作，text_processor.py 负责文本校验，audio_recorder.py 负责录音和数据库写入，audio_player.py 负责音频播放，ui_services.py 提供 Socket 服务（端口 65432 用于 UI 通信）。

## 本阶段目标

实现 Alt 键触发内容匹配与播放功能：
- 用户将鼠标移动到屏幕上任意文本块（如 Notion 中的句子）
- 按下 Alt 键，程序通过 UI Automation 获取鼠标位置下的文本内容
- 将文本与数据库中已有录音记录进行匹配
- 匹配成功：通过 Socket 通知 UI 进程播放对应音频
- 匹配失败：在控制台打印提示信息（本阶段不做其他处理）

## 需要完成的工作

### 1. 新建 ui_automation.py 模块

创建一个独立模块，使用 Windows UI Automation API（通过 comtypes 库调用 COM 接口）获取鼠标位置下的 UI 元素文本。

主要函数 get_text_at_cursor() 通过 ElementFromPoint 获取元素，读取 CurrentName 或 Value 属性。必须处理所有异常（COM 初始化失败、元素不存在等），失败时返回空字符串而不是抛出异常。

### 2. 在 text_processor.py 新增字母序列提取函数

新增 extract_letter_sequence(text, max_chars=300) 函数，用于提取文本中的纯英文字母序列。

规则：只保留英文字母 a-z 和 A-Z，忽略空格、标点、数字、换行符等所有其他字符，统一转为小写，只处理前 max_chars 个字符。

示例："I love you!" 变成 "iloveyou"，"Hello, World." 变成 "helloworld"。

此函数必须在录入和匹配两处复用，确保逻辑完全一致。

### 3. 在 db_manager.py 新增数据库方法

在 DatabaseManager 类中新增：

- migrate_add_letter_sequence() 方法：添加 letter_sequence 字段（TEXT 类型），并为现有记录计算填充该字段。在 init_db() 末尾调用此方法。同时为 letter_sequence 字段创建索引以加速查询。

- get_recording_by_letter_sequence(letter_seq) 方法：根据字母序列查询匹配的录音记录，返回 sqlite3.Row 或 None。复用现有的 _execute_with_retry 机制处理数据库锁定。

### 4. 修改 audio_recorder.py 的录入逻辑

在 _execute_save_transaction() 方法中，插入新记录或更新旧记录时，同时计算并保存 letter_sequence 字段。调用 text_processor 中的 extract_letter_sequence() 函数计算字母序列。

### 5. 新建 alt_trigger.py 模块

创建 AltTriggerListener 类，继承 Thread，设置 daemon=True。功能：

- 使用 pynput 监听 Alt 键（alt_l 和 alt_r）
- 按键后调用 get_text_at_cursor() 获取文本
- 长度超过 600 字符直接跳过
- 调用 extract_letter_sequence() 提取字母序列
- 调用 get_recording_by_letter_sequence() 查询匹配
- 匹配成功：通过 Socket 发送 "PLAY:number" 命令到端口 65432
- 匹配失败：打印 "[AltTrigger] No match found"
- 实现 0.5 秒防抖动机制，避免连续按键重复触发

### 6. 修改 ui_services.py 响应播放命令

在 CommandServer 中添加对 "PLAY:number" 命令的处理，解析 number 后调用 audio_player.play(number, clear_queue=True) 播放指定录音。

### 7. 修改 main.py 集成 Alt 监听

在 MainApp.__init__() 中创建并启动 AltTriggerListener，在 shutdown() 中停止它。

### 8. 修改 requirements.txt

新增 comtypes 依赖。

## 异常处理要求

- UI Automation 失败时返回空字符串，不崩溃
- 数据库操作复用现有的 _execute_with_retry 机制
- Socket 通信失败时记录日志，不影响主流程
- Alt 键必须有 0.5 秒防抖动冷却
- 所有后台线程设置 daemon=True
- SQLite 连接使用 check_same_thread=False

## 代码规范

- 日志格式：[ModuleName] message，如 [AltTrigger] Match found
- 所有 try-except 必须打印有意义的错误信息
- 每个公开函数必须有 docstring，说明 Args 和 Returns
- 不能破坏现有功能，保持向后兼容

## 验证清单

- 在记事本中测试，可以获取光标所在行的文本
- 在 Notion 中测试，可以获取文本块内容
- 匹配成功时能播放对应的录音
- 匹配失败时控制台显示 "[AltTrigger] No match found"
- 连续快速按 Alt 键时有防抖动机制
- UI 未启动时按 Alt 不崩溃
- 数据库迁移后，旧记录的 letter_sequence 字段已填充
- 新录音记录自动生成 letter_sequence


### 阶段二：自动补录功能

# EnREAD 功能开发：Alt 键匹配失败时自动补录

## 前置条件

本阶段基于阶段一已完成的代码。阶段一已实现：Alt 键监听、UI Automation 文本获取、字母序列匹配、匹配成功播放。

## 本阶段目标

在阶段一基础上，当 Alt 键匹配失败时，自动触发 TTS 软件朗读并录制：
- 在当前鼠标位置执行三击，选中文本块
- 等待 TTS 软件的悬浮横条出现
- 使用 OCR 在鼠标上方区域搜索「朗读」两个字
- 找到后点击该位置，触发 TTS 软件朗读
- 现有录音模块会自动录制系统音频并保存
- 如果 OCR 找不到「朗读」，放弃本次并播放提示音

## 悬浮横条位置规律

用户已确认：三击选中文本后，TTS 软件的悬浮横条出现在选中文本块的上方一行，横条左侧起点大约与鼠标横坐标对齐，横条底边在文本块顶部往上几个像素。

## 需要完成的工作

### 1. 新建 auto_record_trigger.py 模块

创建 AutoRecordTrigger 类，封装自动补录逻辑。

#### 三击模拟函数

实现 triple_click(x, y, interval=0.05) 函数，使用 pyautogui 在指定位置快速连续点击三次，每次间隔约 50ms。

#### OCR 搜索函数

实现 ocr_find_text(region, target_text="朗读") 函数，使用 winocr 库（Windows 原生 OCR）在指定屏幕区域搜索目标文字。

搜索区域计算方式（基于鼠标当前位置 x, y）：
- 左边界：x - 20（留一点余量）
- 右边界：x + 300（横条宽度估计）
- 上边界：y - 80（横条在上方）
- 下边界：y - 10（不低于鼠标位置）

截取该区域的屏幕图像，执行 OCR 识别，如果找到「朗读」两个字，返回其在屏幕上的绝对坐标（中心点）；如果未找到，返回 None。

#### 主触发函数

实现 trigger(text) 方法，执行完整的自动补录流程：
1. 获取当前鼠标位置 (x, y)
2. 在 (x, y) 执行三击选中文本
3. 等待 0.3 秒让悬浮横条出现
4. 计算 OCR 搜索区域
5. 调用 OCR 搜索「朗读」
6. 如果找到：点击该位置，返回 True
7. 如果未找到：播放提示音（800Hz, 200ms），返回 False

### 2. 修改 alt_trigger.py 集成自动补录

在 AltTriggerListener 类中：
- 导入 AutoRecordTrigger
- 在 __init__ 中创建 self.auto_record_trigger = AutoRecordTrigger()
- 修改 _process_match() 方法，在匹配失败的分支中调用 self.auto_record_trigger.trigger(text)

### 3. 修改 requirements.txt

新增 winocr 和 pyautogui 依赖。

## 可选配置项

AutoRecordTrigger 类可接受配置字典，支持以下参数：
- ocr_search_offset_y：OCR 搜索区域上方偏移，默认 80 像素
- ocr_search_width：OCR 搜索区域宽度，默认 320 像素
- wait_after_triple_click：三击后等待时间，默认 0.3 秒

## 异常处理要求

- OCR 失败时播放提示音并放弃，不影响主流程
- 三击失败（悬浮条未出现）时，OCR 会找不到按钮，自动走失败流程
- pyautogui 有 FAILSAFE 机制，鼠标移到屏幕角落会抛出异常，需捕获
- 所有异常都要捕获并打印日志，不能导致程序崩溃

## 代码规范

- 日志格式：[AutoRecord] message
- 每个公开函数必须有 docstring
- 失败时调用 winsound.Beep(800, 200) 播放提示音

## 验证清单

- 匹配失败时自动执行三击，文本块被选中
- 悬浮横条出现后，OCR 能找到「朗读」按钮位置
- 点击该位置后 TTS 软件开始朗读
- 录音模块自动录制并保存到数据库
- 新录音保存后，再次按 Alt 能匹配成功并播放
- OCR 找不到「朗读」时，播放提示音并放弃
- 整个自动补录流程中无崩溃或卡死