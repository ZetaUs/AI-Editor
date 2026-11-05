import json
import re
from typing import Callable

import httpx


DEFAULT_ENDPOINT = "https://editor.zztxer.dpdns.org/api/chat"


class AIClient:
    def __init__(self, endpoint: str = DEFAULT_ENDPOINT):
        self.endpoint = endpoint

    def chat_stream(
        self,
        messages: list[dict],
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        full_text = ""
        payload = {"messages": messages, "stream": True}
        with httpx.stream(
            "POST", self.endpoint, json=payload, timeout=httpx.Timeout(120)
        ) as resp:
            if resp.status_code != 200:
                err = resp.read().decode()
                raise RuntimeError(f"AI error {resp.status_code}: {err}")
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        data = json.loads(raw)
                        chunk = self._extract_text(data)
                        if chunk:
                            full_text += chunk
                            if on_chunk:
                                on_chunk(chunk)
                    except json.JSONDecodeError:
                        continue
        return full_text

    @staticmethod
    def _extract_text(data) -> str:
        if isinstance(data, dict):
            if "response" in data and isinstance(data["response"], str):
                return data["response"]
            if "choices" in data and isinstance(data["choices"], list):
                for c in data["choices"]:
                    if isinstance(c, dict):
                        if "delta" in c and isinstance(c["delta"], dict):
                            d = c["delta"]
                            if "content" in d and isinstance(d["content"], str):
                                return d["content"]
                        if "message" in c and isinstance(c["message"], dict):
                            m = c["message"]
                            if "content" in m and isinstance(m["content"], str):
                                return m["content"]
        return ""


def extract_file_ops(text: str) -> list[dict]:
    pattern = r"```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```"
    matches = re.findall(pattern, text)
    for m in matches:
        try:
            data = json.loads(m)
            if isinstance(data, list):
                return [o for o in data if isinstance(o, dict) and "path" in o]
            if isinstance(data, dict) and "path" in data:
                return [data]
        except json.JSONDecodeError:
            continue

    ops = []
    lines = text.split("\n")
    current: dict | None = None
    for line in lines:
        line_stripped = line.strip()
        if line_stripped.startswith(("CREATE ", "MODIFY ", "DELETE ", "RENAME ")):
            if current:
                ops.append(current)
            parts = line_stripped.split(None, 2)
            action = parts[0].lower()
            path = parts[1] if len(parts) > 1 else ""
            current = {"action": action, "path": path, "content": ""}
        elif current is not None:
            current["content"] += line + "\n"
    if current:
        ops.append(current)
    return ops