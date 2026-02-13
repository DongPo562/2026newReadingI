"""
test_api.py - NIM 平台 API 连通性测试工具
用法：python test_api.py [model_id]
  model_id 可选 1,3,5,6,7,8，不传则测试全部模型
"""
import json
import sys
import os
import time
import argparse
import configparser
import urllib.request
import urllib.error
from dotenv import load_dotenv

# 加载 .env 文件（API 密钥、代理等）
load_dotenv()

# ============================================================
# 模型配置（与 ai_service.py 中的 MODEL_REGISTRY 保持一致）
# ============================================================
MODEL_REGISTRY = {
    1: {
        "name": "Kimi 2.5",
        "model": "moonshotai/kimi-k2.5",
        "temperature": 0.7,
        "top_p": 1.0,
        "max_tokens": 640,
        "max_tokens_business": 1024,
    },
    3: {
        "name": "DeepSeek V3.2",
        "model": "deepseek-ai/deepseek-v3.2",
        "temperature": 1,
        "top_p": 0.95,
        "max_tokens": 640,
        "max_tokens_business": 8192,
    },
    5: {
        "name": "MiniMax M2.1",
        "model": "minimaxai/minimax-m2.1",
        "temperature": 1,
        "top_p": 0.95,
        "max_tokens": 640,
        "max_tokens_business": 8192,
    },
    6: {
        "name": "GLM 4.7",
        "model": "z-ai/glm4.7",
        "temperature": 1,
        "top_p": 1,
        "max_tokens": 640,
        "max_tokens_business": 16384,
        "extra_body": {
            "chat_template_kwargs": {
                "enable_thinking": True,
                "clear_thinking": False,
            }
        },
    },
    7: {
        "name": "Doubao Seed 1.8",
        "model": "doubao-seed-1-8-251228",
        "temperature": 1,
        "top_p": 1,
        "max_tokens": 64,
        "max_tokens_business": 8192,
        "api_endpoint": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "api_key_env": "DOUBAO1.8_API_KEY",
        "use_proxy": False,
    },
    8: {
        "name": "DeepSeek Chat",
        "model": "deepseek-chat",
        "temperature": 1,
        "top_p": 0.95,
        "max_tokens": 64,
        "max_tokens_business": 8192,
        "api_endpoint": "https://api.deepseek.com/chat/completions",
        "api_key_env": "DEEPSEEK_API_KEY",
        "use_proxy": False,
    },
}

# API 配置
API_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_TEST_PROMPT = "你好,请介绍一下你自己"
DEFAULT_TIMEOUT = 20  # 测试用超时（秒），比正常使用宽松一些


def get_nim_api_key():
    """获取 API 密钥：优先环境变量，其次 config.ini"""
    key = os.environ.get("NIM_API_KEY", "").strip()
    if key:
        return key
    # 尝试从 config.ini 读取
    try:
        import configparser
        config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
        config.read(config_path)
        key = config.get("QuizTrigger", "api_key", fallback="").strip()
        if key:
            return key
    except Exception:
        pass
    return ""


def _resolve_api_key_for_model(mc, nim_api_key):
    key_env = mc.get("api_key_env")
    if key_env:
        return (os.environ.get(key_env, "") or "").strip(), key_env
    return (nim_api_key or "").strip(), "NIM_API_KEY"


def get_reasoning_enabled():
    """读取 config.ini 的 reasoning 开关，默认关闭。"""
    try:
        config = configparser.ConfigParser()
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
        config.read(config_path)
        return config.getboolean("QuizTrigger", "enable_reasoning", fallback=False)
    except Exception:
        return False


def build_proxy_handler(use_proxy=True):
    """根据环境变量构造代理处理器，便于确认本地代理生效。"""
    if not use_proxy:
        return urllib.request.ProxyHandler({})
    http_proxy = os.environ.get("HTTP_PROXY", "").strip()
    https_proxy = os.environ.get("HTTPS_PROXY", "").strip()
    proxies = {}
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    return urllib.request.ProxyHandler(proxies)


def _extract_text_content(content):
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


def _looks_like_reasoning_param_error(error_text):
    lowered = str(error_text).lower()
    markers = ("chat_template_kwargs", "thinking", "unexpected", "invalid", "unknown")
    return any(x in lowered for x in markers)


def build_business_prompt(content, sentence_content):
    return (
        "用户为英语学习者，母语是中文，请扮演考官，根据以下内容生成一道英语考题。"
        f"内容：{content}，所在句子：{sentence_content}。"
        "请随机选择出一道选择题、填空题或问答题。"
        "请严格以 JSON 格式返回，包含以下字段："
        "type（choice 或 fill 或 qa）、question（题目文本）、"
        "options（选择题时为四个选项的数组，其他题型省略此字段）、answer（标准答案）。"
        "只返回 JSON，不要有其他文字。"
    )


def test_model(model_id, nim_api_key, enable_reasoning, test_prompt, timeout, business_mode):
    """测试单个模型的 API 连通性"""
    mc = MODEL_REGISTRY[model_id]
    endpoint = mc.get("api_endpoint", API_ENDPOINT)
    api_key, key_source = _resolve_api_key_for_model(mc, nim_api_key)
    use_proxy = mc.get("use_proxy", True)
    print(f"\n{'='*60}")
    print(f"  测试模型 #{model_id}: {mc['name']}")
    print(f"  model: {mc['model']}")
    print(f"  endpoint: {endpoint}")
    print(f"  key_env: {key_source}")
    print(f"  proxy: {'ON (use system proxy)' if use_proxy else 'OFF (direct connection)'}")
    print(f"{'='*60}")

    if not api_key:
        print("  [结果] ❌ 未找到 API 密钥")
        print(f"  [详情] 请在环境变量中设置 {key_source}")
        return False

    base_payload = {
        "model": mc["model"],
        "messages": [{"role": "user", "content": test_prompt}],
        "temperature": mc["temperature"],
        "top_p": mc["top_p"],
        "max_tokens": mc["max_tokens_business"] if business_mode else mc["max_tokens"],
        "stream": False,
    }
    if "extra_body" in mc:
        base_payload.update(mc["extra_body"])
    opener = urllib.request.build_opener(build_proxy_handler(use_proxy))

    print(f"  [请求] POST {endpoint}")
    print(f"  [请求] timeout={timeout}s")
    print(f"  [请求] max_tokens={base_payload['max_tokens']}")
    start_time = time.time()

    try:
        payload_candidates = []
        payload_with_reasoning = dict(base_payload)
        reasoning_added = False
        chat_template_kwargs = payload_with_reasoning.get("chat_template_kwargs")
        if isinstance(chat_template_kwargs, dict):
            # 模型自带 chat_template_kwargs 时，仅在已有 thinking 字段时覆盖
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
        status = None
        text = ""
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
            try:
                with opener.open(request, timeout=timeout) as response:
                    status = response.status
                    text = response.read().decode("utf-8")
                    obj = json.loads(text)
                    break
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="ignore")
                if has_reasoning_param and _looks_like_reasoning_param_error(detail):
                    print("  [提示] 当前模型不接受 thinking 参数，自动回退默认请求")
                    continue
                raise

        if obj is None:
            raise RuntimeError("empty response object after all payload attempts")

        elapsed = time.time() - start_time

        # 提取回复内容（兼容不同模型的返回格式）
        content = None
        reasoning = None
        if isinstance(obj, dict):
            choices = obj.get("choices")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") or {}
                content = _extract_text_content(msg.get("content"))
                reasoning = msg.get("reasoning_content")
            # 兜底：顶层 content
            if not content:
                content = _extract_text_content(obj.get("content"))

        # 提取 usage 信息
        usage = obj.get("usage") or {}

        print(f"  [结果] ✅ 成功！HTTP {status}，耗时 {elapsed:.2f}s")
        if content:
            print(f"  [回复] {str(content)[:200]}")
        elif enable_reasoning and reasoning:
            print(f"  [回复(reasoning)] {str(reasoning)[:200]}")
        else:
            print(f"  [回复] (content 为空)")
        if usage:
            print(f"  [用量] prompt_tokens={usage.get('prompt_tokens', '?')}, "
                  f"completion_tokens={usage.get('completion_tokens', '?')}, "
                  f"total_tokens={usage.get('total_tokens', '?')}")
        # 如果 content 和 reasoning 都为空，打印原始响应帮助调试
        if not content and not reasoning:
            print(f"  [原始响应] {text[:500]}")
        return True

    except urllib.error.HTTPError as e:
        elapsed = time.time() - start_time
        detail = e.read().decode("utf-8", errors="ignore")
        print(f"  [结果] ❌ HTTP 错误！状态码 {e.code}，耗时 {elapsed:.2f}s")
        print(f"  [详情] {detail[:300]}")
        return False

    except urllib.error.URLError as e:
        elapsed = time.time() - start_time
        print(f"  [结果] ❌ 网络错误！耗时 {elapsed:.2f}s")
        print(f"  [详情] {e.reason}")
        return False

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"  [结果] ❌ 异常！耗时 {elapsed:.2f}s")
        print(f"  [详情] {type(e).__name__}: {e}")
        return False


def main():
    print("\n" + "#" * 60)
    print("#  NIM 平台 API 连通性测试")
    print("#" * 60)

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("model_id", nargs="?", type=int, help="可选，1,3,5,6,7")
    parser.add_argument("--business", action="store_true", help="使用与业务一致的出题提示词和 max_tokens")
    parser.add_argument("--content", default="keeps adding", help="业务模式下的 content")
    parser.add_argument("--sentence", default="7. It keeps adding onto itself.", help="业务模式下的 sentence_content")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="请求超时秒数")
    parser.add_argument("--prompt", default=DEFAULT_TEST_PROMPT, help="自定义普通测试提示词")
    args = parser.parse_args()

    test_prompt = build_business_prompt(args.content, args.sentence) if args.business else args.prompt

    # 获取默认 NIM API 密钥（部分模型会使用独立 key_env）
    nim_api_key = get_nim_api_key()

    # 显示代理配置
    http_proxy = os.environ.get("HTTP_PROXY", "")
    https_proxy = os.environ.get("HTTPS_PROXY", "")

    safe_api_key = (
        f"{nim_api_key[:12]}...{nim_api_key[-4:]}"
        if len(nim_api_key) >= 16 else "(未设置或长度异常)"
    )
    enable_reasoning = get_reasoning_enabled()
    print(f"\n  NIM API Key: {safe_api_key}")
    print(f"  Default Endpoint: {API_ENDPOINT}")
    print(f"  Timeout: {args.timeout}s")
    print(f"  HTTP_PROXY: {http_proxy or '(未设置)'}")
    print(f"  HTTPS_PROXY: {https_proxy or '(未设置)'}")
    print(f"  Reasoning: {'ON' if enable_reasoning else 'OFF'}")
    print(f"  Business Mode: {'ON' if args.business else 'OFF'}")
    print(f"  Test Prompt: \"{test_prompt}\"")

    # 确定要测试的模型
    if args.model_id is not None:
        target_id = args.model_id
        if target_id not in MODEL_REGISTRY:
            print(f"\n  ❌ 无效的 model_id: {target_id}（可选 1,3,5,6,7,8）")
            sys.exit(1)
        test_ids = [target_id]
    else:
        test_ids = sorted(MODEL_REGISTRY.keys())

    # 逐个测试
    results = {}
    for mid in test_ids:
        results[mid] = test_model(
            mid,
            nim_api_key,
            enable_reasoning,
            test_prompt,
            args.timeout,
            args.business
        )

    # 汇总结果
    print(f"\n\n{'='*60}")
    print("  测试结果汇总")
    print(f"{'='*60}")
    for mid in test_ids:
        mc = MODEL_REGISTRY[mid]
        status = "✅ 通过" if results[mid] else "❌ 失败"
        print(f"  #{mid} {mc['name']:20s} {status}")
    print()

    # 推荐
    passed = [mid for mid in test_ids if results[mid]]
    if passed:
        print(f"  💡 建议在 config.ini 中设置 model_id = {passed[0]}")
    else:
        print("  ⚠️  所有模型均测试失败，请检查网络连接和 API 密钥")


if __name__ == "__main__":
    main()
