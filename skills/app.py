# -*- coding: utf-8 -*-
import streamlit as st
import streamlit.components.v1 as components
import html
import json
import requests
import uuid
from urllib.parse import quote


def _json_for_script(value) -> str:
    """Serialize data without allowing it to terminate an inline script tag."""
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )

st.set_page_config(page_title="Lite-Tutor Pro | 极客导师", page_icon="🤖", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "你好，极客！我是 Lite-Tutor。请在左侧选择我的运行模式，然后输入你的科学或工程问题。"}
    ]

if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = "你是 Lite-Tutor，一名泛理科智能体导师。请用简洁、结构化的中文回答。"

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]

if "current_question" not in st.session_state:
    st.session_state.current_question = ""

if "quiz_mode" not in st.session_state:
    st.session_state.quiz_mode = False
if "current_quiz" not in st.session_state:
    st.session_state.current_quiz = None
if "quiz_keywords" not in st.session_state:
    st.session_state.quiz_keywords = []
if "quiz_type" not in st.session_state:
    st.session_state.quiz_type = None
if "quiz_extra" not in st.session_state:
    st.session_state.quiz_extra = {}
if "waiting_answer" not in st.session_state:
    st.session_state.waiting_answer = False

st.markdown(
    """
<style>
    .stApp { background-color: #f8f9fb; }
    .block-container { padding-top: 2rem; max-width: 950px; }
    h1, h2, h3, h4 { color: #1e293b; font-weight: 700; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;}
    .neon-card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 15px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); color: #334155; font-size: 14px; font-weight: 500;}
    .stChatMessage { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
    .stChatMessage p { color: #1e293b !important; font-size: 16px !important; line-height: 1.7 !important; }
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
    .stTextInput > div > div > input, .stTextArea > div > textarea, .stChatInputContainer { background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; color: #1e293b; }
</style>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.title("⚙️ 战情室控制台")
    st.markdown("---")
    openclaw_url = st.text_input("模型 API Base URL", value="https://api.deepseek.com/v1")
    edge_url = st.text_input(
        "本地 Edge Node URL",
        value="http://127.0.0.1:8000",
        help="API Key 会发送到这个地址用于本地转发，请只填写可信地址。",
    )
    api_key = st.text_input("API Key", type="password")
    model_name = st.text_input("Model", value="deepseek-chat")
    temperature = st.slider("Temperature", min_value=0.0, max_value=1.5, value=0.6, step=0.1)
    max_tokens = st.slider("Max Tokens", min_value=128, max_value=4096, value=1024, step=64)
    st.text_area("System Prompt", key="system_prompt", height=120)

    st.markdown("---")
    st.subheader("🔋 算力自适应模式")
    mode = st.radio(
        "选择导师运行状态：",
        ("Lite 模式 (纯文本云端)", "Standard 模式 (课件增强)", "Pro 模式 (工具增强)"),
        index=1
    )

    st.markdown("---")
    st.subheader("📊 诊断状态看板")
    if "Lite" in mode:
        st.info("当前状态：低功耗云端推理\n\n适合设备：老旧设备、无 GPU 终端\n\n优势：极致普惠教育")
    elif "Standard" in mode:
        st.success("当前状态：课件增强模式\n\n支持：PDF课件检索、来源提示、语义评分\n\n优势：基于本地资料回答")
    else:
        st.warning("当前状态：工具增强模式\n\n支持：知识检索、出题、评分工具\n\n本地代码执行默认关闭，需在可信环境中手动启用")

    st.markdown("---")
    st.subheader("📚 知识库管理")
    uploaded_pdf = st.file_uploader("上传课件PDF", type=["pdf"])
    if uploaded_pdf is not None:
        if st.button("导入到知识库"):
            with st.spinner("正在解析PDF..."):
                try:
                    resp = requests.post(
                        f"{edge_url.rstrip('/')}/upload_pdf",
                        files={"file": (uploaded_pdf.name, uploaded_pdf.getvalue(), "application/pdf")},
                        timeout=30
                    )
                    if resp.ok and resp.json().get("status") == "success":
                        data = resp.json()
                        st.success(f"✅ {data['message']}\n共{data['pages']}页，{data['chars']}字")
                    else:
                        st.error(f"导入失败：{resp.json().get('message', '未知错误')}")
                except Exception as e:
                    st.error(f"连接失败：{e}")

    try:
        src_resp = requests.get(f"{edge_url.rstrip('/')}/knowledge_sources", timeout=3)
        if src_resp.ok:
            sources = src_resp.json().get("sources", [])
            if sources:
                st.markdown("**已导入文档：**")
                for s in sources:
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown(f"• {s}")
                    with col2:
                        if st.button("🗑️", key=f"del_{s}"):
                            try:
                                del_resp = requests.delete(
                                    f"{edge_url.rstrip('/')}/knowledge_source/{quote(s, safe='')}",
                                    timeout=5
                                )
                                if del_resp.ok and del_resp.json().get("status") == "success":
                                    st.success("已删除")
                                    st.rerun()
                                else:
                                    st.error("删除失败")
                            except Exception as e:
                                st.error(f"连接失败：{e}")
    except Exception:
        pass

    st.markdown("---")
    override_sid = st.text_input("会话ID（可手动指定）", value=st.session_state.session_id)
    if override_sid != st.session_state.session_id:
        st.session_state.session_id = override_sid

backend_headers = {}
if api_key.strip():
    backend_headers["X-LiteTutor-API-Key"] = api_key.strip()

# ── 顶部标题 ──
header_left, header_right = st.columns([3, 2], vertical_alignment="center")
with header_left:
    st.title("🛰️ Lite-Tutor 战情室")
    st.caption("课件增强问答 | 自适应教学闭环 | 学习状态追踪")
with header_right:
    status = "已配置" if openclaw_url.strip() else "未配置"
    safe_mode = html.escape(str(mode))
    safe_model = html.escape(model_name)
    safe_session_id = html.escape(st.session_state.session_id)
    st.markdown(
        f"""
        <div class="neon-card hud">
            <div>API 地址：{status}</div>
            <div>当前模式：{safe_mode}</div>
            <div>模型：{safe_model}</div>
            <div>会话ID：{safe_session_id}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(" ")

# ===================== Tab主界面 =====================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🧭 对话学习", "🎯 测验", "📈 掌握曲线", "❌ 错题本", "🧠 思维导图"])

# ==================== Tab1：对话 ====================
with tab1:
    st.subheader("🧭 任务对话")
    adaptive_learning = st.toggle(
        "启用自适应教学闭环",
        value=False,
        help="按“诊断 → 针对性讲解 → 测验 → 补救”的流程学习，并把结果写入掌握曲线。",
    )
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"] if isinstance(msg["content"], str) else msg["content"])

    def _fetch_edge_tools(base_url: str):
        try:
            resp = requests.get(f"{base_url.rstrip('/')}/tools", timeout=8)
            if resp.ok:
                return resp.json().get("tools", [])
        except Exception:
            return []
        return []

    def _call_edge_tool(base_url: str, name: str, arguments: dict):
        try:
            if name == "edge_compute_sandbox":
                payload = {
                    "code": arguments.get("code", ""),
                    "language": arguments.get("language", "python"),
                    "timeout": arguments.get("timeout", 10)
                }
                resp = requests.post(f"{base_url.rstrip('/')}/solve", json=payload, timeout=20)
                if resp.ok:
                    return json.dumps(resp.json(), ensure_ascii=False)
                return f"Tool execution failed: HTTP {resp.status_code}"
            if name == "edge_knowledge_rag":
                payload = {"query": arguments.get("query", ""), "mode": "hybrid", "n_results": 2}
                resp = requests.post(f"{base_url.rstrip('/')}/search", json=payload, timeout=20)
                if resp.ok:
                    return json.dumps(resp.json(), ensure_ascii=False)
                return f"Tool execution failed: HTTP {resp.status_code}"
            if name == "edge_quiz_generator":
                payload = {
                    "question": arguments.get("question", ""),
                    "context": arguments.get("context", ""),
                    "n_results": arguments.get("n_results", 2),
                    "difficulty": arguments.get("difficulty", "medium"),
                    "question_type": arguments.get("question_type", "varied")
                }
                resp = requests.post(
                    f"{base_url.rstrip('/')}/quiz", json=payload,
                    headers=backend_headers, timeout=20,
                )
                if resp.ok:
                    return json.dumps(resp.json(), ensure_ascii=False)
                return f"Tool execution failed: HTTP {resp.status_code}"
            if name == "edge_answer_grader":
                payload = {
                    "answer": arguments.get("answer", ""),
                    "keywords": arguments.get("keywords", []),
                    "min_hit": arguments.get("min_hit", 1),
                    "session_id": st.session_state.session_id,
                    "question": st.session_state.current_question,
                    "question_type": arguments.get("question_type", "short_answer"),
                    "expected_answer": arguments.get("expected_answer"),
                }
                resp = requests.post(
                    f"{base_url.rstrip('/')}/grade", json=payload,
                    headers=backend_headers, timeout=20,
                )
                if resp.ok:
                    return json.dumps(resp.json(), ensure_ascii=False)
                return f"Tool execution failed: HTTP {resp.status_code}"
            return f"Unknown tool: {name}"
        except Exception as e:
            return f"Tool execution error: {e}"

    if prompt := st.chat_input("向极客导师提问..."):
        st.session_state.current_question = prompt
        user_content = prompt
        display_text = prompt

        st.session_state.messages.append({"role": "user", "content": user_content})
        with st.chat_message("user"):
            st.markdown(display_text)

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            if adaptive_learning:
                try:
                    tutor_resp = requests.post(
                        f"{edge_url.rstrip('/')}/tutor",
                        json={
                            "session_id": st.session_state.session_id,
                            "user_input": prompt,
                        },
                        headers=backend_headers,
                        timeout=60,
                    )
                    tutor_data = tutor_resp.json()
                    if tutor_resp.ok and tutor_data.get("status") == "success":
                        full_response = tutor_data.get("response", "")
                    else:
                        full_response = f"教学流程调用失败：{tutor_data.get('message', tutor_resp.text)}"
                except Exception as e:
                    full_response = f"教学流程连接失败：{e}"
            elif not openclaw_url.strip():
                full_response = "OpenClaw Base URL 未配置。"
            else:
                messages = []
                if st.session_state.system_prompt.strip():
                    messages.append({"role": "system", "content": st.session_state.system_prompt.strip()})
                rag_sources = []
                if "Lite" not in mode and edge_url.strip():
                    try:
                        search_resp = requests.post(
                            f"{edge_url.rstrip('/')}/search",
                            json={"query": prompt, "mode": "hybrid", "n_results": 3},
                            timeout=15,
                        )
                        search_data = search_resp.json()
                        if search_resp.ok and not search_data.get("fallback_required", True):
                            context = search_data.get("context", "")
                            rag_sources = search_data.get("sources", [])
                            if context:
                                messages.append({
                                    "role": "system",
                                    "content": (
                                        "以下是从学生课件中检索到的资料。优先依据这些资料回答；"
                                        "若资料不足，请明确说明，不要编造。\n\n" + context
                                    ),
                                })
                    except Exception:
                        rag_sources = []
                messages.extend(st.session_state.messages)
                headers = {"Content-Type": "application/json; charset=utf-8"}
                if api_key.strip():
                    headers["Authorization"] = f"Bearer {api_key.strip()}"
                tools = []
                if "Pro" in mode and edge_url.strip():
                    tools = _fetch_edge_tools(edge_url)
                payload = {
                    "model": model_name.strip(),
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                }
                if tools:
                    payload["tools"] = tools
                    payload["tool_choice"] = "auto"
                endpoint = f"{openclaw_url.rstrip('/')}/chat/completions"
                try:
                    resp = requests.post(endpoint, json=payload, headers=headers, timeout=60)
                    if resp.ok:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices and "message" in choices[0]:
                            message = choices[0]["message"]
                            tool_calls = message.get("tool_calls", [])
                            if tool_calls and tools:
                                messages.append(message)
                                for call in tool_calls:
                                    name = call.get("function", {}).get("name", "")
                                    raw_args = call.get("function", {}).get("arguments", "{}")
                                    try:
                                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                                    except Exception:
                                        args = {}
                                    result = _call_edge_tool(edge_url, name, args)
                                    messages.append({
                                        "role": "tool",
                                        "tool_call_id": call.get("id", ""),
                                        "name": name,
                                        "content": result
                                    })
                                payload["messages"] = messages
                                follow = requests.post(endpoint, json=payload, headers=headers, timeout=60)
                                if follow.ok:
                                    follow_data = follow.json()
                                    follow_choices = follow_data.get("choices", [])
                                    if follow_choices and "message" in follow_choices[0]:
                                        full_response = follow_choices[0]["message"].get("content", "")
                                    else:
                                        full_response = "OpenClaw 返回内容为空。"
                                else:
                                    full_response = f"OpenClaw 请求失败，HTTP {follow.status_code}"
                            else:
                                full_response = message.get("content", "")
                        else:
                            full_response = "OpenClaw 返回内容为空。"
                    else:
                        full_response = f"OpenClaw 请求失败，HTTP {resp.status_code}"
                except Exception as e:
                    full_response = f"OpenClaw 调用失败：{e}"

                if full_response and rag_sources:
                    source_labels = []
                    for item in rag_sources:
                        label = item.get("source", "课件")
                        if item.get("page"):
                            label += f" 第{item['page']}页"
                        if label not in source_labels:
                            source_labels.append(label)
                    full_response += "\n\n> 课件来源：" + "；".join(source_labels)

            message_placeholder.markdown(full_response)

        st.session_state.messages.append({"role": "assistant", "content": full_response})

# ==================== Tab2：测验 ====================
with tab2:
    st.subheader("🎯 测验模式")

    # ── 难度 & 题型选择 ──
    diff_col, type_col = st.columns(2)
    with diff_col:
        difficulty = st.selectbox(
            "📊 难度",
            options=["easy", "medium", "hard"],
            format_func=lambda x: {"easy": "🟢 简单", "medium": "🟡 中等", "hard": "🔴 困难"}[x],
            index=1,
            key="quiz_difficulty"
        )
    with type_col:
        question_type = st.selectbox(
            "📝 题型",
            options=["varied", "choice", "fill", "short_answer", "true_false"],
            format_func=lambda x: {
                "varied": "🎲 混合随机", "choice": "📋 选择题",
                "fill": "✏️ 填空题", "short_answer": "📝 简答题", "true_false": "✅ 判断题"
            }[x],
            key="quiz_question_type"
        )
        # 在题型选择下方添加一行说明
        type_hints = {
            "varied": "AI会随机选择题型",
            "choice": "4选1，选出正确答案",
            "fill": "填入缺失的关键术语",
            "short_answer": "用一段话阐述",
            "true_false": "判断对错并简述理由"
        }
        st.caption(type_hints.get(question_type, ""))

    quiz_topic = st.text_input("输入考察主题（如：SQL查询、递归、哈希表）", key="quiz_topic_input")
    col_q1, col_q2 = st.columns([2, 8])
    with col_q1:
        gen_btn = st.button("📝 出题", use_container_width=True)

    if gen_btn and quiz_topic.strip():
        with st.spinner("AI正在出题..."):
            try:
                resp = requests.post(
                    f"{edge_url.rstrip('/')}/quiz",
                    json={
                        "question": quiz_topic.strip(),
                        "n_results": 2,
                        "difficulty": difficulty,
                        "question_type": question_type
                    },
                    headers=backend_headers,
                    timeout=20
                )
                if resp.ok and resp.json().get("status") == "success":
                    data = resp.json()
                    st.session_state.current_quiz = data.get("quiz", "")
                    st.session_state.quiz_keywords = data.get("keywords", [])
                    st.session_state.current_question = quiz_topic.strip()
                    st.session_state.quiz_type = data.get("question_type", "short_answer")
                    st.session_state.quiz_extra = {
                        k: v for k, v in data.items()
                        if k not in ("status", "quiz", "keywords", "context", "question_type")
                    }
                    st.session_state.waiting_answer = True
                    st.rerun()
                else:
                    data = resp.json()
                    st.error(f"出题失败：{data.get('message', resp.text)}")
            except Exception as e:
                st.error(f"连接失败：{e}")

    if st.session_state.waiting_answer and st.session_state.current_quiz:
        q_type = st.session_state.get("quiz_type", "short_answer")
        extra = st.session_state.get("quiz_extra", {})

        # 题型图标映射
        type_icon = {
            "choice": "📋 选择题", "fill": "✏️ 填空题",
            "short_answer": "📝 简答题", "true_false": "✅ 判断题"
        }
        type_badge = type_icon.get(q_type, "📝 题目")
        safe_badge = html.escape(type_badge)
        safe_quiz = html.escape(str(st.session_state.current_quiz))

        st.markdown(
            f"""<div style="background:#f0f7ff;border-left:4px solid #2E75B6;
            border-radius:8px;padding:15px;margin:10px 0;">
            <span style="background:#2E75B6;color:white;padding:2px 10px;border-radius:12px;font-size:0.8em;">{safe_badge}</span>
            <br><br><b>{safe_quiz}</b></div>""",
            unsafe_allow_html=True
        )

        with st.form("answer_form", clear_on_submit=True):
            if q_type == "choice":
                options = extra.get("options", {})
                if options and len(options) >= 2:
                    option_keys = sorted(options.keys())
                    user_answer = st.radio(
                        "请选择你的答案：",
                        options=option_keys,
                        format_func=lambda x: f"{x}. {options[x]}",
                        horizontal=True,
                        key="choice_radio"
                    )
                else:
                    st.caption("（选项未正常生成，请直接输入答案字母）")
                    user_answer = st.text_input(
                        "输入你的选项（A/B/C/D）：",
                        placeholder="如 A",
                        key="choice_fallback"
                    )
            elif q_type == "fill":
                user_answer = st.text_area(
                    "你的填空答案：",
                    height=80,
                    placeholder="填入空白处的内容（如有多个空，用分号；隔开）",
                    key="fill_text_input"
                )
            elif q_type == "true_false":
                user_answer = st.radio(
                    "你的判断：",
                    options=["正确", "错误"],
                    horizontal=True,
                    key="tf_radio"
                )
            else:
                user_answer = st.text_area(
                    "你的回答：",
                    height=120,
                    placeholder="在这里输入你的答案...",
                    key="sa_text_input"
                )

            col_s1, col_s2 = st.columns([2, 8])
            with col_s1:
                submitted = st.form_submit_button("✅ 提交答案", use_container_width=True)
            with col_s2:
                give_up = st.form_submit_button("🔄 换一题", use_container_width=True)

        if give_up:
            st.session_state.waiting_answer = False
            st.session_state.current_quiz = None
            st.session_state.quiz_keywords = []
            st.session_state.quiz_type = None
            st.session_state.quiz_extra = {}
            st.rerun()

        if submitted and user_answer:
            final_answer = str(user_answer).strip()
            if not final_answer:
                st.warning("请输入或选择你的答案")
            else:
                with st.spinner("AI评分中..."):
                    try:
                        grade_resp = requests.post(
                            f"{edge_url.rstrip('/')}/grade",
                            json={
                                "answer": final_answer,
                                "keywords": st.session_state.quiz_keywords,
                                "session_id": st.session_state.session_id,
                                "question": st.session_state.current_quiz,
                                "question_type": q_type,
                                "expected_answer": (
                                    extra.get("blanks") if q_type == "fill"
                                    else extra.get("correct")
                                ),
                            },
                            headers=backend_headers,
                            timeout=20
                        )
                        gdata = grade_resp.json()
                        if grade_resp.ok and gdata.get("status") == "success":
                            result = gdata.get("result", "")
                            feedback = gdata.get("feedback", "")
                            matched = gdata.get("matched_keywords", [])

                            if result == "校验通过":
                                st.success("✅ 回答正确！")
                            else:
                                st.error("❌ 回答有误")

                            if feedback:
                                safe_feedback = html.escape(str(feedback))
                                st.markdown(
                                    f"""<div style="background:#fffbeb;border-left:4px solid #f59e0b;
                                    border-radius:8px;padding:12px;margin:8px 0;">
                                    🤖 <b>AI点评：</b>{safe_feedback}</div>""",
                                    unsafe_allow_html=True
                                )
                            if matched:
                                st.markdown(f"**✨ 命中知识点：** {', '.join(matched)}")

                            st.session_state.waiting_answer = False
                            st.session_state.current_quiz = None
                            st.session_state.quiz_type = None
                            st.session_state.quiz_extra = {}

                            # 再来一题按钮
                            if st.button("➡️ 再来一题", use_container_width=False):
                                st.rerun()
                        else:
                            st.error(f"评分失败：{gdata.get('message', grade_resp.text)}")

                    except Exception as e:
                        st.error(f"评分失败：{e}")

# ==================== Tab3：掌握曲线 ====================
with tab3:
    st.subheader("📈 知识点掌握曲线")
    sid = st.session_state.session_id

    try:
        resp = requests.get(f"{edge_url.rstrip('/')}/learning_stats", params={"session_id": sid}, timeout=5)
        records = resp.json().get("records", []) if resp.ok else []
    except Exception:
        records = []

    if not records:
        st.info("还没有答题记录，去「测验」Tab完成几道题再来看吧～")
    else:
        kw_stats = {}
        for r in records:
            for kw in r.get("keywords", []):
                if kw not in kw_stats:
                    kw_stats[kw] = {"total": 0, "pass": 0, "history": []}
                kw_stats[kw]["total"] += 1
                passed = r["result"] == "校验通过"
                if passed:
                    kw_stats[kw]["pass"] += 1
                kw_stats[kw]["history"].append({
                    "time": r.get("timestamp", "")[:10],
                    "passed": passed
                })

        if kw_stats:
            labels = list(kw_stats.keys())
            values = [round(kw_stats[k]["pass"] / kw_stats[k]["total"] * 100) for k in labels]
            totals = [kw_stats[k]["total"] for k in labels]
            passes = [kw_stats[k]["pass"] for k in labels]

            # ── 顶部概览卡片 ──
            overall = round(sum(passes) / sum(totals) * 100) if sum(totals) > 0 else 0
            metric_cols = st.columns(4)
            metric_cols[0].metric("📊 总体掌握度", f"{overall}%")
            metric_cols[1].metric("📝 总答题数", sum(totals))
            metric_cols[2].metric("✅ 通过数", sum(passes))
            metric_cols[3].metric("🏷️ 知识点数", len(labels))

            # 颜色映射函数
            def _mastery_color(pct):
                if pct >= 80:
                    return "#22c55e"  # green
                elif pct >= 60:
                    return "#2E75B6"  # blue
                elif pct >= 40:
                    return "#f59e0b"  # amber
                elif pct >= 20:
                    return "#f97316"  # orange
                else:
                    return "#ef4444"  # red

            chart_html = f"""
            <div id="curve_chart" style="width:100%;height:420px;"></div>
            <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
            <script>
            (function() {{
                var chart = echarts.init(document.getElementById('curve_chart'));
                var resizeTimer;
                window.addEventListener('resize', function() {{
                    clearTimeout(resizeTimer);
                    resizeTimer = setTimeout(function() {{ chart.resize(); }}, 100);
                }});

                var labels = {_json_for_script(labels)};
                var values = {_json_for_script(values)};
                var totals = {_json_for_script(totals)};
                var passes = {_json_for_script(passes)};

                // 为每个数据点生成颜色
                var pointColors = values.map(function(v) {{
                    if (v >= 80) return '#22c55e';
                    if (v >= 60) return '#2E75B6';
                    if (v >= 40) return '#f59e0b';
                    if (v >= 20) return '#f97316';
                    return '#ef4444';
                }});

                chart.setOption({{
                    backgroundColor: 'transparent',
                    color: ['#2E75B6'],
                    tooltip: {{
                        trigger: 'axis',
                        renderMode: 'richText',
                        backgroundColor: 'rgba(255,255,255,0.95)',
                        borderColor: '#e2e8f0',
                        borderWidth: 1,
                        textStyle: {{ color: '#1e293b', fontSize: 13 }},
                        formatter: function(params) {{
                            var p = params[0];
                            var idx = p.dataIndex;
                            return p.name + '\\n'
                                + '掌握度：' + values[idx] + '%\\n'
                                + '通过：' + passes[idx] + ' / 总答题：' + totals[idx];
                        }}
                    }},
                    grid: {{ top: 20, right: 40, bottom: 60, left: 50 }},
                    xAxis: {{
                        type: 'category',
                        data: labels,
                        axisLine: {{ lineStyle: {{ color: '#cbd5e1' }} }},
                        axisTick: {{ show: false }},
                        axisLabel: {{
                            color: '#475569',
                            fontSize: 12,
                            rotate: labels.length > 6 ? 30 : 0,
                            interval: 0
                        }}
                    }},
                    yAxis: {{
                        type: 'value',
                        min: 0,
                        max: 105,
                        axisLine: {{ show: false }},
                        axisTick: {{ show: false }},
                        splitLine: {{
                            lineStyle: {{ color: '#f1f5f9', type: 'dashed' }}
                        }},
                        axisLabel: {{
                            color: '#94a3b8',
                            fontSize: 11,
                            formatter: '{{value}}%'
                        }}
                    }},
                    series: [
                        {{
                            name: '掌握度',
                            type: 'bar',
                            data: values.map(function(v, i) {{
                                return {{
                                    value: v,
                                    itemStyle: {{
                                        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                                            {{ offset: 0, color: pointColors[i] }},
                                            {{ offset: 1, color: pointColors[i] + '40' }}
                                        ]),
                                        borderRadius: [6, 6, 0, 0],
                                        borderColor: pointColors[i],
                                        borderWidth: 1
                                    }}
                                }};
                            }}),
                            barWidth: '50%',
                            label: {{
                                show: true,
                                position: 'top',
                                color: '#475569',
                                fontSize: 11,
                                fontWeight: 'bold',
                                formatter: '{{c}}%'
                            }},
                            emphasis: {{
                                itemStyle: {{
                                    shadowBlur: 10,
                                    shadowOffsetX: 0,
                                    shadowColor: 'rgba(0,0,0,0.15)'
                                }}
                            }},
                            animationDelay: function(idx) {{ return idx * 80; }}
                        }},
                        {{
                            name: '掌握度趋势',
                            type: 'line',
                            data: values,
                            smooth: true,
                            symbol: 'emptyCircle',
                            symbolSize: 10,
                            lineStyle: {{ color: '#6366f1', width: 2.5, type: 'dashed' }},
                            itemStyle: {{ color: '#6366f1', borderWidth: 2 }},
                            z: 1,
                            emphasis: {{ scale: 1.3 }}
                        }}
                    ]
                }});

                // 标记线 - 达标线
                chart.setOption({{
                    series: [
                        {{ markLine: {{
                            silent: true,
                            symbol: 'none',
                            lineStyle: {{ color: '#22c55e', type: 'dotted', width: 2 }},
                            label: {{ color: '#22c55e', fontSize: 11, formatter: '🎯 达标线 70%' }},
                            data: [{{ yAxis: 70 }}]
                        }} }},
                        {{ }}  // second series — no markLine
                    ]
                }});

                chart.resize();
            }})();
            </script>
            """
            components.html(chart_html, height=440)

            # ── 知识点掌握度卡片 ──
            st.markdown("---")
            st.markdown("**📋 知识点详情：**")
            card_cols = st.columns(min(len(labels), 4) or 1)
            for idx, kw in enumerate(labels):
                with card_cols[idx % len(card_cols)]:
                    pct = values[idx]
                    ttl = totals[idx]
                    ps = passes[idx]
                    color = _mastery_color(pct)
                    # 进度条
                    emoji = "🌟" if pct >= 80 else "📘" if pct >= 60 else "📙" if pct >= 40 else "📕"
                    safe_kw = html.escape(str(kw))
                    st.markdown(
                        f"""<div style="background:#ffffff;border:1px solid {color}30;
                        border-radius:12px;padding:12px;margin:4px 0;
                        box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                            <span style="color:#334155;font-weight:600;font-size:0.9em;">{emoji} {safe_kw}</span>
                            <span style="color:{color};font-weight:700;font-size:1.1em;">{pct}%</span>
                        </div>
                        <div style="background:#f1f5f9;border-radius:6px;height:6px;overflow:hidden;">
                            <div style="background:{color};height:100%;width:{pct}%;border-radius:6px;
                            transition: width 0.6s ease;"></div>
                        </div>
                        <div style="color:#94a3b8;font-size:0.75em;margin-top:4px;">
                            {ps}/{ttl} 通过
                        </div></div>""",
                        unsafe_allow_html=True
                    )

# ==================== Tab4：错题本 ====================
with tab4:
    st.subheader("❌ 错题本")
    try:
        resp = requests.get(f"{edge_url.rstrip('/')}/learning_stats", params={"session_id": st.session_state.session_id}, timeout=5)
        records = resp.json().get("records", []) if resp.ok else []
    except Exception:
        records = []

    wrong = [r for r in records if r["result"] != "校验通过"]

    if not wrong:
        st.success("太棒了，暂时没有错题！")
    else:
        st.markdown(f"共 **{len(wrong)}** 道错题")
        for i, r in enumerate(wrong, 1):
            with st.expander(f"错题 {i}：{r['question'][:40] if r['question'] else '（无题目记录）'}"):
                st.markdown(f"**🕐 时间：** {r['timestamp'][:19].replace('T', ' ')}")
                st.markdown(f"**❓ 题目关键词：** {', '.join(r['keywords']) if r['keywords'] else '无'}")
                st.markdown(f"**✍️ 你的回答：** {r['answer']}")
                st.markdown(f"**✅ 命中关键词：** {', '.join(r['hits']) if r['hits'] else '无'}")
                missed = [k for k in r['keywords'] if k not in r['hits']]
                if missed:
                    st.markdown(f"**💡 漏掉的关键词：** {', '.join(missed)}")
                if r.get("feedback"):
                    safe_feedback = html.escape(str(r["feedback"]))
                    st.markdown(
                        f"""<div style="background:#fffbeb;border-left:4px solid #f59e0b;
                        border-radius:8px;padding:10px;margin:6px 0;">
                        🤖 <b>AI点评：</b>{safe_feedback}</div>""",
                        unsafe_allow_html=True
                    )
                if st.button("🔁 重新练习", key=f"retry_{i}"):
                    retry_topic = "、".join(r.get("keywords", [])[:3]) or r.get("question", "")
                    if retry_topic:
                        try:
                            retry_resp = requests.post(
                                f"{edge_url.rstrip('/')}/quiz",
                                json={
                                    "question": retry_topic,
                                    "n_results": 2,
                                    "difficulty": "easy",
                                    "question_type": r.get("question_type", "varied"),
                                },
                                headers=backend_headers,
                                timeout=20,
                            )
                            retry_data = retry_resp.json()
                            if retry_resp.ok and retry_data.get("status") == "success":
                                st.session_state.current_quiz = retry_data.get("quiz", "")
                                st.session_state.quiz_keywords = retry_data.get("keywords", [])
                                st.session_state.current_question = retry_topic
                                st.session_state.quiz_type = retry_data.get("question_type", "short_answer")
                                st.session_state.quiz_extra = {
                                    key: value for key, value in retry_data.items()
                                    if key not in ("status", "quiz", "keywords", "context", "question_type")
                                }
                                st.session_state.waiting_answer = True
                                st.toast("已生成一道针对性复习题，请切换到“测验”页。")
                                st.rerun()
                            else:
                                st.error(f"重新出题失败：{retry_data.get('message', retry_resp.text)}")
                        except Exception as e:
                            st.error(f"重新出题失败：{e}")

# ==================== Tab5：思维导图 ====================
with tab5:
    st.subheader("🧠 知识点思维导图")
    try:
        resp = requests.get(f"{edge_url.rstrip('/')}/learning_stats", params={"session_id": st.session_state.session_id}, timeout=5)
        records = resp.json().get("records", []) if resp.ok else []
    except Exception:
        records = []

    all_keywords = []
    for r in records:
        all_keywords.extend(r.get("keywords", []))
    unique_kws = list(dict.fromkeys(all_keywords))

    # 手动添加知识点
    col_add1, col_add2 = st.columns([4, 1])
    with col_add1:
        extra_kw = st.text_input("手动添加知识点到图谱", placeholder="输入知识点名称，回车添加")
    with col_add2:
        st.markdown("<br>", unsafe_allow_html=True)
        add_btn = st.button("➕ 添加", use_container_width=True)
    
    if "extra_kws" not in st.session_state:
        st.session_state.extra_kws = []
    if add_btn and extra_kw.strip():
        if extra_kw.strip() not in st.session_state.extra_kws:
            st.session_state.extra_kws.append(extra_kw.strip())
            st.rerun()
    
    # 合并自动+手动的知识点
    all_keywords = all_keywords + st.session_state.extra_kws
    unique_kws = list(dict.fromkeys(all_keywords))
    if not unique_kws:
        st.info("还没有学习记录，完成几道题后这里会自动生成知识点思维导图～")
    else:
        st.markdown("💡 **节点可以拖拽，滚轮缩放画布 | 双击节点高亮关联**")

        # ── 构建更丰富的图谱数据 ──
        nodes = []
        links = []
        categories = [
            {"name": "核心", "itemStyle": {"color": "#2E75B6"}},
            {"name": "题目", "itemStyle": {"color": "#8b5cf6"}},
            {"name": "知识点", "itemStyle": {"color": "#f59e0b"}},
            {"name": "手动", "itemStyle": {"color": "#22c55e"}},
        ]

        # 中心节点
        nodes.append({
            "name": "Lite-Tutor",
            "symbolSize": 60,
            "category": 0,
            "label": {"fontSize": 14, "fontWeight": "bold"},
            "itemStyle": {"shadowBlur": 8, "shadowColor": "rgba(46,117,182,0.3)"}
        })

        # 从学习记录构建题目-知识点关联
        question_map = {}
        for r in records[-20:]:
            q = r.get("question", "")[:14] or "其他"
            kws = r.get("keywords", [])
            if q not in question_map:
                question_map[q] = {"kws": set(), "pass": 0, "total": 0}
            question_map[q]["kws"].update(kws)
            question_map[q]["total"] += 1
            if r["result"] == "校验通过":
                question_map[q]["pass"] += 1

        added_kws = set()
        node_idx = 1
        for q, info in list(question_map.items())[:8]:
            mastery = round(info["pass"] / info["total"] * 100) if info["total"] > 0 else 0
            node_size = 28 + mastery * 0.2  # 掌握度越高节点越大
            nodes.append({
                "name": q,
                "symbolSize": node_size,
                "category": 1,
                "label": {"fontSize": 10},
                "mastery": mastery
            })
            links.append({
                "source": "Lite-Tutor",
                "target": q,
                "lineStyle": {"width": 1.5, "opacity": 0.5}
            })
            for kw in list(info["kws"])[:4]:
                if kw not in added_kws:
                    nodes.append({
                        "name": kw,
                        "symbolSize": 22,
                        "category": 2,
                        "label": {"fontSize": 9},
                    })
                    added_kws.add(kw)
                links.append({
                    "source": q,
                    "target": kw,
                    "lineStyle": {"width": 1, "opacity": 0.35}
                })

        # 手动添加的知识点用不同颜色
        for extra in st.session_state.extra_kws:
            if extra not in added_kws:
                nodes.append({
                    "name": extra,
                    "symbolSize": 26,
                    "category": 3,
                    "label": {"fontSize": 10, "fontWeight": "bold"},
                    "itemStyle": {"borderWidth": 2, "borderColor": "#22c55e"}
                })
                links.append({
                    "source": "Lite-Tutor",
                    "target": extra,
                    "lineStyle": {"width": 2, "color": "#22c55e", "opacity": 0.5, "type": "dashed"}
                })
                added_kws.add(extra)

        # 根据节点数量动态调整力参数
        node_count = len(nodes)
        repulsion_val = max(150, min(800, node_count * 35))
        gravity_val = 0.08 + node_count * 0.003
        edge_len = max(60, min(180, 160 - node_count * 4))

        mind_html = f"""
        <div id="mind_chart" style="width:100%;height:460px;max-width:100%;overflow:hidden;"></div>
        <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
        <script>
        (function() {{
            var chartDom = document.getElementById('mind_chart');
            var chart = echarts.init(chartDom);

            // 自适应大小
            function resizeChart() {{
                var w = chartDom.clientWidth;
                chart.resize({{ width: w, height: Math.min(460, w * 0.75) }});
            }}
            var resizeTimer;
            window.addEventListener('resize', function() {{
                clearTimeout(resizeTimer);
                resizeTimer = setTimeout(resizeChart, 100);
            }});

            var nodes = {_json_for_script(nodes)};
            var links = {_json_for_script(links)};

            // 为每条边添加微小曲度防止完全重叠
            links = links.map(function(link, i) {{
                return {{
                    ...link,
                    lineStyle: {{
                        ...(link.lineStyle || {{}}),
                        curveness: 0.08 + (i % 3) * 0.06
                    }}
                }};
            }});

            chart.setOption({{
                backgroundColor: 'transparent',
                tooltip: {{
                    renderMode: 'richText',
                    backgroundColor: 'rgba(255,255,255,0.95)',
                    borderColor: '#e2e8f0',
                    textStyle: {{ color: '#1e293b', fontSize: 12 }},
                    formatter: function(p) {{
                        if (p.dataType === 'node') {{
                            var cat = ['核心', '题目', '知识点', '手动添加'][p.data.category || 0];
                            var info = p.name + '\\n类型：' + cat;
                            if (p.data.mastery !== undefined) {{
                                info += '\\n掌握度：' + p.data.mastery + '%';
                            }}
                            return info;
                        }}
                        return p.source + ' → ' + p.target;
                    }}
                }},
                series: [{{
                    type: 'graph',
                    layout: 'force',
                    roam: 'move',
                    draggable: true,
                    center: ['50%', '50%'],
                    categories: {_json_for_script(categories)},
                    label: {{
                        show: true,
                        position: 'right',
                        color: '#334155',
                        fontSize: 11,
                        distance: 6,
                        formatter: function(p) {{
                            return p.name.length > 8 ? p.name.slice(0, 8) + '…' : p.name;
                        }}
                    }},
                    labelLayout: {{
                        hideOverlap: true
                    }},
                    lineStyle: {{
                        color: 'rgba(148,163,184,0.35)',
                        width: 1.2,
                        curveness: 0.1,
                        opacity: 0.6
                    }},
                    emphasis: {{
                        focus: 'adjacency',
                        lineStyle: {{ width: 3 }},
                        itemStyle: {{ shadowBlur: 12, shadowColor: 'rgba(0,0,0,0.2)' }},
                        label: {{ fontSize: 13, fontWeight: 'bold' }}
                    }},
                    roam: true,
                    scaleLimit: {{ min: 0.4, max: 2.5 }},
                    force: {{
                        initIterations: 150,
                        layoutAnimation: true,
                        repulsion: {repulsion_val},
                        gravity: {gravity_val},
                        edgeLength: [{edge_len}, {edge_len + 80}],
                        friction: 0.6
                    }},
                    nodes: nodes,
                    links: links,
                    animationDuration: 1500,
                    animationEasingUpdate: 'quinticInOut'
                }}]
            }});

            // 点击节点聚焦
            chart.on('click', function(params) {{
                if (params.dataType === 'node') {{
                    chart.dispatchAction({{
                        type: 'focusNodeAdjacency',
                        seriesIndex: 0,
                        dataIndex: params.dataIndex
                    }});
                }}
            }});

            // 双击恢复全局视图
            chart.on('dblclick', function() {{
                chart.dispatchAction({{
                    type: 'unfocusNodeAdjacency',
                    seriesIndex: 0
                }});
            }});

            resizeChart();
        }})();
        </script>
        """
        components.html(mind_html, height=580)
        st.caption("💡 拖拽节点调整布局 | 滚轮缩放 | 点击节点高亮关联 | 双击空白恢复全局视图")
