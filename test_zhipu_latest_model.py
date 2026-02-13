import json
import os
import re
import sys
import urllib.error
import urllib.request

from dotenv import load_dotenv


API_URL = " https://open.bigmodel.cn/api/coding/paas/v4"
MODEL_ID = "glm-5"
SYSTEM_PROMPT = "你是一个有用的AI助手。"
USER_PROMPT = "你好，请介绍一下自己。"


def main() -> int:
    load_dotenv()
    api_key = os.getenv("ZHIPU_API_KEY", "").strip()
    if not api_key:
        print("ERROR: 未读取到 ZHIPU_API_KEY，请检查 .env 配置。")
        return 1

    payload = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        "temperature": 1.0,
        "stream": True,
    }

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content_type = response.headers.get("Content-Type", "")
            is_stream = "text/event-stream" in content_type.lower()
            if is_stream:
                text = _read_stream_response(response)
                if not text:
                    print("API 返回成功，但流式内容为空。")
                    return 4
                print("API 调用成功，模型可用（stream=true）。")
                print(f"Model: {MODEL_ID}")
                print(f"Prompt: {USER_PROMPT}")
                print("Reply:")
                print(text)
                return 0
            body = response.read().decode("utf-8", errors="replace")
            data = json.loads(body)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP ERROR: {exc.code}")
        print(err_body)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"REQUEST ERROR: {exc}")
        return 3

    choices = data.get("choices") or []
    if not choices:
        print("API 返回成功但没有 choices 字段，完整响应如下：")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 4

    message = choices[0].get("message", {})
    content = message.get("content", "")
    usage = data.get("usage", {})

    print("API 调用成功，模型可用。")
    print(f"Model: {data.get('model', MODEL_ID)}")
    print(f"Prompt: {USER_PROMPT}")
    print("Reply:")
    print(content)
    if usage:
        print("Usage:")
        print(json.dumps(usage, ensure_ascii=False, indent=2))

    return 0


def _read_stream_response(response) -> str:
    chunks = []
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            continue
        delta = ((event.get("choices") or [{}])[0].get("delta") or {}).get("content")
        if isinstance(delta, str):
            chunks.append(delta)

    text = "".join(chunks).strip()
    # Fallback: handle occasional escaped \u payload fragments from some gateways.
    if "\\u" in text:
        try:
            text = re.sub(r"\\\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
        except Exception:  # noqa: BLE001
            pass
    return text


if __name__ == "__main__":
    sys.exit(main())
