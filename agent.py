import json
from typing import Optional

from utils import build_system_prompt, run_ollama, run_ollama_tool, tool_registry
from config import CONTROLLER_MODEL
from conversation import conversation

# ===== Agent 逻辑 =====
def process_agent_cycle(user_text: str, image_path: Optional[str] = None, code: int = 0):
    """
    Main orchestration:
    1. Append user input to conversation
    2. Call DeepSeek, expect JSON dict describing an action
    3. If action == call_tool: call corresponding tool, append tool result, then call DeepSeek again
    4. If action == final_answer: return to frontend
    5. If action == clarify: return clarify question
    """

    conversation.change_status(code=code)
    # 1. add user message
    conversation.append("user", user_text if user_text is not None else "")
    conversation.trim()

    
    max_tool_loops = 15  # 最多连续调用工具次数
    loop_count = 0

    while True:
        # call DeepSeek
        ds_raw = ""
        full_prompt = f"""SYSTEM:\n{build_system_prompt(image_path)}\n\nCONVERSATION:\n{conversation.as_prompt()}\n\nREPLY_AS_JSON_ONLY:\n"""
        for chunk in run_ollama(CONTROLLER_MODEL, full_prompt):
            ds_raw += chunk
            yield chunk  # 实时推送到前端
        # try:
            # ds_raw = call_deepseek_with_system(conversation.as_prompt(), image_path)
        # except Exception as e:
        #     return {"error": f"DeepSeek 调用失败: {e}", "final": True, "answer": "模型调用失败，请稍后重试。"}

        ds_text = ds_raw.strip()
        try:
            parsed = json.loads(ds_text)
        except Exception:
            try:
                start = ds_text.index("{")
                end = ds_text.rindex("}") + 1
                parsed = json.loads(ds_text[start:end])
            except Exception:
                conversation.append("assistant", ds_text)
                conversation.trim()
                yield f"\n[System] 模型输出解析错误: {ds_text}\n"
                break

        action = parsed.get("action")

        if action == "call_tool":
            loop_count += 1
            if loop_count > max_tool_loops:
                conversation.append("assistant", "工具调用次数过多，终止。")
                conversation.trim()
                yield "\n[System] 工具调用次数过多，终止。\n"
                break

            tool_name = parsed.get("tool_name")
            tool_input = parsed.get("tool_input", {})

            if image_path and tool_input.get("image_path") in (None, "", "<image_path>"):
                tool_input["image_path"] = image_path

            if tool_name not in tool_registry:
                conversation.append("assistant", f"调用了未知工具{tool_name}。")
                conversation.trim()
                yield f"\n[System] 未知工具: {tool_name}\n"
                break

            
            try:
                # 工具调用提示
                yield f"\n[System] 调用工具 {tool_name} 中...\n"
                tool_result = tool_registry[tool_name].func(tool_input)
                yield tool_result + "\n"
            except Exception as e:
                conversation.append("assistant", f"工具 {tool_name} 调用失败: {e}")
                conversation.trim()
                yield f"\n[System] 工具调用失败：{e}\n"
                break

            conversation.append("tool", tool_result)
            conversation.trim()
            conversation.change_status(1, loop_count)
            # callback DeepSeek

        elif action == "final_answer":
            answer = parsed.get("answer", "")
            conversation.append("assistant", answer)
            conversation.trim()
            yield f"\n[Final Answer]\n{answer}\n"
            break

        elif action == "clarify":
            q = parsed.get("question", "")
            conversation.append("assistant", q)
            conversation.trim()
            yield f"\n[Clarification Needed]\n{q}\n"
            break

        else:
            conversation.append("assistant", ds_text)
            conversation.trim()
            yield f"\n[System] 未知 action: {action}\n"
            break