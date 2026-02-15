"""
ai_service.py - AI 出题与批改服务
"""
import json
import os
import re
import time
import socket
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from PyQt6.QtCore import QObject, pyqtSignal
from config_loader import app_config

# 加载 .env 文件（API 密钥、代理等）
load_dotenv()

# ============================================================
# 模型配置映射表
# key = config.ini 中的 model_id 数字
# 每个模型包含：model（模型标识）、temperature、top_p、max_tokens、extra_body（可选）
# 注意：出题和批改场景不需要思维链，已移除 extra_body 中的 thinking 参数，
# 避免模型把 token 全花在 reasoning_content 上导致 content 为空。
# ============================================================
MODEL_REGISTRY = {
    1: {
        "model": "moonshotai/kimi-k2.5",
        "temperature": 0.7,
        "top_p": 1.0,
        "max_tokens": 1024,
    },
    3: {
        "model": "deepseek-ai/deepseek-v3.2",
        "temperature": 1,
        "top_p": 0.95,
        "max_tokens": 8192,
    },
    5: {
        "model": "minimaxai/minimax-m2.1",
        "temperature": 1,
        "top_p": 0.95,
        "max_tokens": 8192,
    },
    6: {
        "model": "z-ai/glm4.7",
        "temperature": 1,
        "top_p": 1,
        "max_tokens": 16384,
        "extra_body": {
            "chat_template_kwargs": {
                "enable_thinking": True,
                "clear_thinking": False,
            }
        },
    },
    7: {
        "model": "doubao-seed-1-8-251228",
        "temperature": 1,
        "top_p": 1,
        "max_tokens": 8192,
        "api_endpoint": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "api_key_env": "DOUBAO1.8_API_KEY",
        "use_proxy": False,
    },
    8: {
        "model": "deepseek-chat",
        "temperature": 1,
        "top_p": 0.95,
        "max_tokens": 8192,
        "api_endpoint": "https://api.deepseek.com/chat/completions",
        "api_key_env": "DEEPSEEK_API_KEY",
        "use_proxy": False,
    },
}

# 默认 model_id，当配置值无效时使用
DEFAULT_MODEL_ID = 3
REQUEST_RETRY_COUNT = 1
REQUEST_RETRY_BACKOFF_SECONDS = 0.8
RETRYABLE_HTTP_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

DEFAULT_QUESTION_PROMPT_TEMPLATE = """你是一位资深英语老师，致力于通过多样化的题型帮助学生深度掌握知识点。请根据用户选中的知识点【{{content}}】（上下文：【{{sentence_content}}】），灵活设计一道英语练习题。请根据知识点的特性（单词/短语/句子）从以下题型中随机选择最合适的一种：

1. **选择题 (type: choice)**：
- 同义词/反义词辨析（如：accumulate vs collect）；
- 固定搭配介词选择（如：disconnect [from]）；
- 短语含义理解（选出正确解释）。

2. **填空题 (type: fill)**：
- 语境完形：挖空原句或新句中的关键短语，考察拼写；
- 翻译填空：给出中文提示，要求填写对应的英文短语（如：把某人引向歧途 -> [take sb down the wrong road]）。

3. **问答题 (type: qa)**：
- 句子改写 (Rewrite)：给出一个意思相近的句子，要求用本知识点改写；
- 造句练习 (Make a sentence)：要求用该知识点造一个新句；
- 概念解释 (Explain)：询问该词与近义词的区别（如：confidence vs charisma）或深度解释概念含义。

**输出约束**：
- 必须严格返回合法的 JSON 格式，不要包含 ```json 标记或其他文字。
- JSON 字段必须包含：type (仅限 choice/fill/qa), question (题目文本), options (仅选择题需要，4个字符串的数组), answer (标准答案字符串)。
- 题目设计应避免与原句完全重复，尽量提供新的语境或视角。"""

DEFAULT_GRADE_PROMPT_TEMPLATE = """用户是一名母语为中文的英语学习者，以下是一道英语考题和用户的答案，请批改。题目：{{question}}，用户答案：{{user_answer}}，标准答案：{{answer}}。首先告诉用户答对或者答错。如果答对了，给出简单赞赏语句，并且对题目做出分析和讲解。如果答错了，回复非常遗憾，然后给出错题讲解。请直接返回批改文本。"""

DEFAULT_EMOJI_PROMPT_TEMPLATE = """What emoji(s) best represent the meaning of "{{content}}"? Reply with 1 to 3 emojis only, nothing else."""


class AIServiceSignals(QObject):
    question_ready = pyqtSignal(int, str)
    question_failed = pyqtSignal(int, str)


class LLMRequestError(RuntimeError):
    def __init__(self, message, retryable):
        super().__init__(message)
        self.retryable = retryable


class AIService:
    def __init__(self, model_id=None, enable_reasoning=None, api_timeout=None, enable_fallback=True, enable_retry=True):
        self._override_model_id = model_id
        self._override_enable_reasoning = enable_reasoning
        self._override_api_timeout = api_timeout
        self.enable_fallback = enable_fallback
        self.enable_retry = enable_retry
        self.reasoning_only_drop_count = 0
        self.signals = AIServiceSignals()
        self.executor = ThreadPoolExecutor(max_workers=2)
        self._last_model_id = None
        self._log_config()

    def _log_config(self):
        mid = self._get_model_id()
        mc = MODEL_REGISTRY.get(mid, {})
        print(
            f"[AIService] Primary model #{mid}: "
            f"{mc.get('model', 'unknown')}"
        )
        print(f"[AIService] Fallback order: {self._get_model_candidates()}")
        print(f"[AIService] Reasoning enabled: {self._get_enable_reasoning()} (final answer uses content only)")
        print(f"[AIService] reasoning-only fallback count: {self.reasoning_only_drop_count}")
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        if proxy:
            print(f"[AIService] Proxy: {proxy}")

    def _get_model_id(self):
        if self._override_model_id is not None:
            try:
                mid = int(self._override_model_id)
                if mid in MODEL_REGISTRY:
                    return mid
            except Exception:
                pass
        try:
            mid = int(app_config.quiz_trigger_model_id)
            if mid in MODEL_REGISTRY:
                return mid
        except Exception:
            pass
        return DEFAULT_MODEL_ID

    def _get_model_candidates(self):
        primary = self._get_model_id()
        ordered = [primary, DEFAULT_MODEL_ID] + sorted(MODEL_REGISTRY.keys())
        dedup = []
        for mid in ordered:
            if mid in MODEL_REGISTRY and mid not in dedup:
                dedup.append(mid)
        return dedup

    def _get_enable_reasoning(self):
        if self._override_enable_reasoning is not None:
            return bool(self._override_enable_reasoning)
        return app_config.quiz_trigger_enable_reasoning

    def _get_api_timeout(self):
        if self._override_api_timeout is not None:
            return float(self._override_api_timeout)
        return app_config.quiz_trigger_api_timeout

    def _get_endpoint(self):
        return app_config.quiz_trigger_api_endpoint

    def _get_api_key(self):
        return os.environ.get("NIM_API_KEY") or app_config.quiz_trigger_api_key

    def _check_model_change(self):
        app_config.reload()
        current_mid = self._get_model_id()
        if current_mid != self._last_model_id:
            print(f"[AIService] Model changed: #{self._last_model_id} -> #{current_mid}")
            self._last_model_id = current_mid
            self._log_config()

    def _load_prompt_template(self, prompt_name, file_path, default_template):
        if file_path:
            try:
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        text = f.read().strip()
                    if text:
                        print(f"[AIService] Prompt '{prompt_name}' source=config file={file_path}")
                        return text
                    print(f"[AIService] Prompt '{prompt_name}' file is empty, fallback to default")
                else:
                    print(f"[AIService] Prompt '{prompt_name}' file not found: {file_path}; fallback to default")
            except Exception as e:
                print(f"[AIService] Prompt '{prompt_name}' read failed: {e}; fallback to default")
        print(f"[AIService] Prompt '{prompt_name}' source=default")
        return default_template

    def _render_prompt_template(self, template, variables):
        text = template or ""
        for key, value in variables.items():
            text = text.replace("{{" + key + "}}", "" if value is None else str(value))
        return text.strip()

    def shutdown(self):
        self.executor.shutdown(wait=False, cancel_futures=True)

    def generate_question(self, question_id, content, sentence_content):
        return self.executor.submit(
            self._generate_question_worker, question_id, content, sentence_content
        )

    def grade_answer(self, question_json, user_answer):
        return self.executor.submit(self._grade_answer_worker, question_json, user_answer)

    def generate_emoji(self, content):
        return self.executor.submit(self._generate_emoji_worker, content)

    def _build_question_prompt(self, content, sentence_content):
        template = self._load_prompt_template(
            "quiz_question",
            app_config.quiz_trigger_question_prompt_file,
            DEFAULT_QUESTION_PROMPT_TEMPLATE,
        )
        return self._render_prompt_template(
            template,
            {"content": content, "sentence_content": sentence_content},
        )

    def _generate_local_fill(self, content, sentence_content):
        question_text = (sentence_content or "").replace(content, "", 1)
        if not question_text:
            question_text = f"Fill in the blank:  ({content})"
        return json.dumps(
            {"type": "fill", "question": question_text, "answer": content},
            ensure_ascii=False
        )

    def _generate_question_worker(self, question_id, content, sentence_content):
        self._check_model_change()
        fallback_json = self._generate_local_fill(content, sentence_content)
        try:
            raw = self._request_llm(self._build_question_prompt(content, sentence_content))
            parsed = self._safe_parse_question_json(raw)
            if parsed is None:
                print("[AIService] JSON parse failed, fallback to local fill question")
                return "failed", fallback_json
            normalized = json.dumps(parsed, ensure_ascii=False)
            return "success", normalized
        except Exception as e:
            print(f"[AIService] Generate question failed: {e}")
            return "failed", fallback_json

    def _grade_answer_worker(self, question_json, user_answer):
        self._check_model_change()
        data = json.loads(question_json)
        template = self._load_prompt_template(
            "quiz_grade",
            app_config.quiz_trigger_grade_prompt_file,
            DEFAULT_GRADE_PROMPT_TEMPLATE,
        )
        prompt = self._render_prompt_template(
            template,
            {
                "question": data.get("question", ""),
                "user_answer": user_answer,
                "answer": data.get("answer", ""),
            },
        )
        try:
            return self._request_llm(prompt)
        except Exception as e:
            print(f"[AIService] Grade failed, fallback to local comment: {e}")
            return self._build_local_grade_feedback(data, user_answer)

    def _build_local_grade_feedback(self, question_data, user_answer):
        answer = str(question_data.get("answer", "")).strip()
        question = str(question_data.get("question", "")).strip()
        guess = str(user_answer or "").strip()
        if not guess:
            return f"你还没有输入答案。参考答案是：{answer}。建议先尝试作答，再查看讲解。"
        if answer and guess.lower() == answer.lower():
            return f"回答正确，做得很好！题目是：{question}。参考答案：{answer}。"
        return (
            "很遗憾，这次回答不正确。"
            f"你的答案：{guess}。参考答案：{answer}。"
            "建议回到原句重新理解关键词和语法结构。"
        )

    def _build_emoji_prompt(self, content):
        template = self._load_prompt_template(
            "emoji",
            app_config.emoji_trigger_prompt_file,
            DEFAULT_EMOJI_PROMPT_TEMPLATE,
        )
        return self._render_prompt_template(template, {"content": content})

    def _extract_emojis(self, text):
        if not text:
            return ""

        flag_pair = r"(?:[\U0001F1E6-\U0001F1FF]{2})"
        base_symbol = r"(?:[\U0001F300-\U0001FAFF\u2600-\u27BF])"
        modifier = r"(?:[\uFE0E\uFE0F]|[\U0001F3FB-\U0001F3FF])"
        zwj_piece = rf"(?:\u200D(?:{base_symbol}|{flag_pair})(?:{modifier})*)"
        emoji_unit = rf"(?:{flag_pair}|{base_symbol})(?:{modifier})*(?:{zwj_piece})*"

        matches = re.findall(emoji_unit, text)
        if not matches:
            return ""
        return "".join(matches[:3])

    def _generate_emoji_worker(self, content):
        self._check_model_change()
        raw = self._request_llm(self._build_emoji_prompt(content))
        emojis = self._extract_emojis(raw)
        if emojis:
            return emojis
        raise RuntimeError("No valid emoji extracted from model response")

    def _looks_like_reasoning_param_error(self, error_text):
        lowered = str(error_text).lower()
        markers = ("chat_template_kwargs", "thinking", "unexpected", "invalid", "unknown")
        return any(x in lowered for x in markers)

    def _extract_text_content(self, content):
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks = []
            for item in content:
                if isinstance(item, str):
                    chunks.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type", "")).lower()
                if item_type in ("text", "output_text"):
                    text = item.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
            merged = "".join(chunks).strip()
            return merged if merged else None
        return None

    def _request_llm(self, prompt):
        self._check_model_change()
        errors = []
        model_list = self._get_model_candidates() if self.enable_fallback else [self._get_model_id()]
        retry_count = REQUEST_RETRY_COUNT if self.enable_retry else 0
        
        for model_id in model_list:
            mc = MODEL_REGISTRY[model_id]
            model_name = mc["model"]
            for attempt in range(retry_count + 1):
                try:
                    return self._request_llm_once(model_id, prompt)
                except LLMRequestError as e:
                    attempt_label = f"model#{model_id}/{attempt + 1}"
                    errors.append(f"{attempt_label} {e}")
                    is_last_attempt = attempt >= retry_count
                    if e.retryable and not is_last_attempt:
                        sleep_s = REQUEST_RETRY_BACKOFF_SECONDS * (attempt + 1)
                        print(
                            f"[AIService] Retryable error on {attempt_label}: {e}; "
                            f"retry after {sleep_s:.1f}s"
                        )
                        time.sleep(sleep_s)
                        continue
                    print(f"[AIService] Skip {model_name}: {e}")
                    break
        summary = " | ".join(errors[-3:]) if errors else "unknown reason"
        raise RuntimeError(f"All model attempts failed: {summary}")

    def _request_llm_once(self, model_id, prompt):
        mc = MODEL_REGISTRY[model_id]
        endpoint = mc.get("api_endpoint", self._get_endpoint())
        api_key_env = mc.get("api_key_env")
        if api_key_env:
            api_key = (os.environ.get(api_key_env) or "").strip()
        else:
            api_key = self._get_api_key()
        if not endpoint:
            raise LLMRequestError("api_endpoint is empty", retryable=False)
        if not api_key:
            if api_key_env:
                raise LLMRequestError(f"api_key is empty: env {api_key_env}", retryable=False)
            raise LLMRequestError("api_key is empty", retryable=False)

        print("[AIService] Prompt begin >>>")
        print(prompt)
        print("[AIService] <<< Prompt end")

        enable_reasoning = self._get_enable_reasoning()
        api_timeout = self._get_api_timeout()
        base_payload = {
            "model": mc["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": mc["temperature"],
            "top_p": mc["top_p"],
            "max_tokens": mc["max_tokens"],
            "stream": False,
        }

        # 部分模型可能需要 extra_body
        if "extra_body" in mc:
            base_payload.update(mc["extra_body"])

        payload_candidates = []
        payload_with_reasoning = dict(base_payload)
        reasoning_added = False
        chat_template_kwargs = payload_with_reasoning.get("chat_template_kwargs")
        if isinstance(chat_template_kwargs, dict):
            # 对模型已声明的 chat_template_kwargs，仅在存在 thinking 字段时覆盖开关
            if "thinking" in chat_template_kwargs:
                payload_with_reasoning["chat_template_kwargs"] = dict(chat_template_kwargs)
                payload_with_reasoning["chat_template_kwargs"]["thinking"] = enable_reasoning
                reasoning_added = True
        else:
            payload_with_reasoning["chat_template_kwargs"] = {"thinking": enable_reasoning}
            reasoning_added = True

        if reasoning_added:
            payload_candidates.append((payload_with_reasoning, True))
        payload_candidates.append((base_payload, False))

        obj = None
        for payload, has_reasoning_param in payload_candidates:
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                endpoint,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            print(
                f"[AIService] Request model#{model_id} ({mc['model']}), "
                f"endpoint={endpoint}, timeout={api_timeout}s, "
                f"thinking={enable_reasoning if has_reasoning_param else 'default'}, "
                f"proxy={mc.get('use_proxy', True)}"
            )
            try:
                start_time = time.time()
                use_proxy = mc.get("use_proxy", True)
                if use_proxy:
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler())
                else:
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(request, timeout=api_timeout) as response:
                    elapsed_time = time.time() - start_time
                    text = response.read().decode("utf-8")
                    print(f"[AIService] Response received in {elapsed_time:.2f}s")
                    obj = json.loads(text)
                    break
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="ignore")
                retryable = e.code in RETRYABLE_HTTP_CODES
                err = LLMRequestError(f"HTTP {e.code}: {detail[:200]}", retryable)
                if has_reasoning_param and self._looks_like_reasoning_param_error(detail):
                    print("[AIService] reasoning parameter not accepted, retry without it")
                    continue
                raise err from e
            except urllib.error.URLError as e:
                raise LLMRequestError(f"URL error: {e.reason}", retryable=True) from e
            except socket.timeout as e:
                raise LLMRequestError(f"Timeout: {e}", retryable=True) from e
            except TimeoutError as e:
                raise LLMRequestError(f"Timeout: {e}", retryable=True) from e
            except json.JSONDecodeError as e:
                raise LLMRequestError(f"JSON decode error: {e}", retryable=True) from e

        if obj is None:
            raise LLMRequestError("Empty LLM response object", retryable=True)

        # 提取回复内容（兼容不同模型返回格式）
        content = None
        reasoning = None
        if isinstance(obj, dict):
            choices = obj.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") or {}
                content = self._extract_text_content(msg.get("content"))
                reasoning = msg.get("reasoning_content")
            # 兜底：顶层 content
            if not content:
                content = self._extract_text_content(obj.get("content"))

        if not content:
            if reasoning:
                self.reasoning_only_drop_count += 1
                print(
                    "[AIService] reasoning-only response dropped; "
                    f"count={self.reasoning_only_drop_count}"
                )
                raise LLMRequestError(
                    "LLM response has no final content (reasoning exists but not used)",
                    retryable=False
                )
            raise LLMRequestError("LLM response has no content", retryable=False)

        print("[AIService] Response begin >>>")
        print(content)
        print("[AIService] <<< Prompt end")
        return content

    def _safe_parse_question_json(self, raw_text):
        # 第一层：直接解析完整文本
        try:
            data = json.loads(raw_text)
            return self._normalize_question(data)
        except Exception:
            pass

        # 第二层：提取第一个 JSON 对象块
        match = re.search(r"\{[\s\S]*\}", raw_text)
        if match:
            try:
                data = json.loads(match.group(0))
                return self._normalize_question(data)
            except Exception:
                pass

        # 第三层：交由上层 fallback（本地填空题）
        return None

    def _normalize_question(self, data):
        if not isinstance(data, dict):
            return None
        qtype = str(data.get("type", "")).strip().lower()
        question = str(data.get("question", "")).strip()
        answer = data.get("answer", "")
        if not qtype or not question:
            return None
        normalized = {
            "type": qtype if qtype in ("choice", "fill", "qa") else "fill",
            "question": question,
            "answer": str(answer).strip(),
        }
        if normalized["type"] == "choice":
            options = data.get("options", [])
            if not isinstance(options, list):
                return None
            cleaned = [str(x).strip() for x in options if str(x).strip()]
            if len(cleaned) != 4:
                return None
            normalized["options"] = cleaned
        return normalized
