import os
import gradio as gr
import hashlib

from config import TMP_IMAGE_DIR
from agent import process_agent_cycle


image_cache = {}  # {hash: file_path}
image_last = ""
text_last = ""


def save_image_to_disk(pil_img) -> str:
    if pil_img is None:
        return None
    img_bytes = pil_img.tobytes()
    img_hash = hashlib.sha256(img_bytes).hexdigest()
    # 如果已有相同图片
    if img_hash in image_cache:
        return image_cache[img_hash]
    # ts = int(time.time() * 1000)
    path = os.path.join(TMP_IMAGE_DIR, f"img_{img_hash[:8]}.png")
    pil_img.save(path)
    image_cache[img_hash] = path
    return path


def gradio_respond(user_text: str, image):
    """
    Called by Gradio: runs agent cycle and returns text output to UI.
    If agent asks clarification (final==False and clarify==True), we present the question.
    """
    global image_last
    global text_last
    image_path = save_image_to_disk(image) if image is not None else None
    if image_last == image_path and text_last == user_text:
        code = 2
    elif image_last == image_path and text_last != user_text:
        text_last = user_text
        code = 3
    else:
        image_last = image_path
        text_last = user_text
        code = 0
    full_text = ""
    for chunk in process_agent_cycle(user_text=user_text, image_path=image_path, code=code):
        full_text += chunk  # 累加已生成内容
        yield full_text  


def build_ui():
    with gr.Blocks(title="图文 Agent (DeepSeek 主, LLaVA 工具)") as ui:
        gr.Markdown("# 图文Agent 原型\nDeepSeek 作为主 Agent；LLaVA 作为 tool。")
        with gr.Row():
            txt = gr.Textbox(label="输入文本", placeholder="在此输入你的问题或指令（可包含图片）", lines=3)
            img = gr.Image(label="上传图片（可选）", type="pil")
        btn = gr.Button("发送")
        out = gr.Textbox(label="模型输出", lines=30)
        btn.click(fn=gradio_respond, inputs=[txt, img], outputs=[out])
    return ui