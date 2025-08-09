import sys
import time
import json
import base64
import shutil
import requests
import subprocess
from typing import Any, List, Dict, Callable, Optional

from config import OLLAMA_URL, VISION_MODEL, CONTROLLER_MODEL, DEEPSEEK_SYSTEM_PROMPT

# ===== 启动 Ollama 端口 =====
def find_ollama_executable():
    # 1) shutil.which
    for name in ("ollama", "ollama.exe"):
        p = shutil.which(name)
        if p:
            return p

    # 2) try `where` (Windows)
    if sys.platform.startswith("win"):
        try:
            r = subprocess.run(["where", "ollama"], capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.splitlines()[0].strip()
        except Exception:
            pass

    return None


def start_ollama_service():
    ollama_path = find_ollama_executable()
    # 启动 ollama 本地服务
    process = subprocess.Popen([ollama_path, "serve"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # 等待服务启动
    for _ in range(20):
        try:
            r = requests.get("http://localhost:11434/api/tags", timeout=1)
            if r.status_code == 200:
                print("✅ Ollama 服务已启动")
                return process
        except requests.exceptions.RequestException:
            pass
        time.sleep(0.5)
    
    raise RuntimeError("❌ 启动 Ollama 服务失败")


# ===== Ollama Tool Model调用 =====
def run_ollama_tool(model_name: str, prompt: str, images: Optional[List[str]] = None):
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False
    }
    if images:
        # Include image paths; exact Ollama server may require slightly different format in your environment.
        payload["images"] = images

    try:
        resp = requests.post(OLLAMA_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
        # Ollama's response shape might vary; commonly there's a top-level text/response
        # Try several keys commonly returned.
        if "response" in data:
            return data["response"]
        if "text" in data:
            return data["text"]
        # fallback: pretty print full json
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        # Raise a descriptive error for the caller to handle
        raise RuntimeError(f"Ollama call failed for model {model_name}: {e}")
    
    
# ===== Ollama 流式调用 =====
def run_ollama(model_name: str, prompt: str):
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": True
    }

    with requests.post(OLLAMA_URL, json=payload, stream=True) as r:
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                data = json.loads(line)
                chunk = data.get("response", "")
                if chunk:
                    yield chunk
            except json.JSONDecodeError:
                continue


# ============= 工具注册（tool registry） =============
class Tool:
    def __init__(self, name: str, func: Callable[..., str], description: str = ""):
        self.name = name
        self.func = func
        self.description = description

tool_registry: Dict[str, Tool] = {}

def register_tool(tool: Tool):
    tool_registry[tool.name] = tool

# LLaVA 调用工具（接受 text + optional image_path）
def llava_tool(tool_input: Dict[str, Any]) -> str:
    """
    tool_input expects keys: "text" (str) and optional "image_path" (str)
    returns textual result from llava model.
    """
    text = tool_input.get("text", "")
    image_path = tool_input.get("image_path")
    # Build prompt for llava: include clear instruction and the textual query
    llava_prompt = f"SYSTEM: You are LLaVA, a vision-language model. Follow the user's query.\nUSER: {text}\nASSISTANT:"
    images = [image_encoder(image_path)] if image_path else None
    # Slightly larger timeout for image ops
    return run_ollama_tool(VISION_MODEL, llava_prompt, images=images)

# register llava
register_tool(Tool(name="llava", func=llava_tool, description="Vision-language LLM tool, prefer ENG input"))

def build_system_prompt(image_path: Optional[str] = None) -> str:
    tool_list_str = "\nTOOLS AVAILABLE\n:"
    tool_list_str += "\n".join(
        [f"- {name}: {tool.description}" for name, tool in tool_registry.items()]
    )
    if image_path:
        img = "IMAGE PATH:\n" + image_path + "\n\n"
        return  DEEPSEEK_SYSTEM_PROMPT + img + tool_list_str + "\n\nEND."
    else:
        return  DEEPSEEK_SYSTEM_PROMPT + tool_list_str + "\n\nEND."

def image_encoder(image_path: str) -> str:
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    # Convert to base64 string
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    return image_b64