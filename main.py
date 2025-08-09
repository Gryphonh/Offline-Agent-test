from ui import build_ui
from utils import start_ollama_service


# ============= CLI 启动 =============
if __name__ == "__main__":
    start_ollama_service()
    print("Starting Gradio app... (ensure Ollama is running locally on port 11434)")
    ui = build_ui()
    ui.queue().launch(server_name="127.0.0.1", server_port=7860, share=False)