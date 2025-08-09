from typing import List, Dict, Optional
from config import MAX_ROUNDS

# ============= 会话管理 =============
class Conversation:
    def __init__(self, max_rounds: int = MAX_ROUNDS):
        # history is list of dicts: {"role": "user|assistant|tool", "content": "..."}
        self.history: List[Dict[str, str]] = []  # memory
        self.max_rounds = max_rounds
        self.status = "\n[System Status]: New Topic\n"

    def append(self, role: str, content: str):
        self.history.append({"role": role, "content": content})

    def trim(self):
        # keep last max_rounds * 2 entries (user+assistant pairs). If tool messages included, ensure not to lose context badly.
        max_entries = self.max_rounds * 2 + 4  # small buffer for tool messages
        if len(self.history) > max_entries:
            # keep tail
            self.history = self.history[-max_entries:]

    def as_prompt(self) -> str:
        # convert to a single prompt for DeepSeek: include system prompt header + conversation lines
        lines = []
        if self.status == "\n[System Status]: New Topic\n":
            self.history = self.history[-1:]
        for m in self.history:
            # mark tool outputs explicitly
            if m["role"] == "tool":
                lines.append(f"[TOOL RESULT]: {m['content']}")
            else:
                lines.append(f"{m['role'].upper()}: {m['content']}")
        return "\n".join(lines) + self.status
    
    def change_status(self, code: int, times: Optional[int] = 0):
        if code == 0:
            self.status = "\n[System Status]: New Topic\n"
        elif code == 1:
            self.status = f"\n[System Status]: Tool Callback times {times}\n"
        elif code == 2:
            self.status = "\n[System Status]: User Repeat\n"
        elif code == 3:
            self.status = "\n[System Status]: User Supplement\n"
        

# instantiate global conversation (for prototype single-session)
conversation = Conversation()