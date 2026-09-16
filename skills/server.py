import os
import subprocess
import re
import uuid
import hashlib
import sys
from collections import Counter
from threading import Lock
from typing import Optional, Dict, Any, List, Literal
from fastapi import FastAPI, Header, UploadFile, File, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn
import json
from pathlib import Path
from datetime import datetime
import httpx
try:
    import pymupdf as fitz
except ImportError:  # Compatibility with older PyMuPDF releases.
    import fitz
import tempfile


from rag_builder import LocalRAGKnowledgeBase
from edge_tool import get_tool_schemas
from assessment import grade_structured_answer

BASE_DIR = Path(__file__).resolve().parent


def _runtime_path(env_name: str, default_name: str) -> Path:
    configured = Path(os.getenv(env_name, default_name)).expanduser()
    return configured if configured.is_absolute() else BASE_DIR / configured


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE = os.getenv("DEEPSEEK_BASE", "https://api.deepseek.com/v1").rstrip("/")
ALLOW_CODE_EXECUTION = os.getenv("LITETUTOR_ENABLE_CODE_EXECUTION", "false").lower() in {
    "1", "true", "yes", "on"
}

class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

app = FastAPI(title="LiteTutor Edge Node", default_response_class=UTF8JSONResponse)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "llm_configured": bool(DEEPSEEK_API_KEY),
        "code_execution_enabled": ALLOW_CODE_EXECUTION,
    }

def _tokenize(text: str) -> List[str]:
    parts = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.lower())
    tokens: List[str] = []
    for part in parts:
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            tokens.extend(part[i:i + 2] for i in range(max(1, len(part) - 1)))
        elif len(part) > 1:
            tokens.append(part)
    return tokens


def _api_key(override: Optional[str] = None) -> str:
    """Prefer a per-request key from the local UI; never persist it."""
    return (override or DEEPSEEK_API_KEY).strip()


def _stable_variant(value: str, count: int) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % count

def _extract_keywords(text: str, limit: int = 4) -> List[str]:
    tokens = _tokenize(text)
    if not tokens:
        return []
    counts = Counter(tokens)
    return [w for w, _ in counts.most_common(limit)]

def _build_quiz(question: str, context: Optional[str] = None, n_results: int = 2,
                difficulty: str = "medium", question_type: str = "varied",
                api_key: Optional[str] = None):
    """出题：支持难度选择和多样题型
    difficulty: easy | medium | hard
    question_type: varied(混合) | choice(选择) | fill(填空) | short_answer(简答) | true_false(判断)
    返回: (context, keywords, quiz_text, question_type, options)
    """
    working_context = context.strip() if context else ""
    if not working_context:
        working_context = rag_db.query_knowledge_hybrid(question, n_results=n_results)

    difficulty_guide = {
        "easy": "基础概念题，考察最核心的定义和简单理解，适合初学者",
        "medium": "综合理解题，考察知识点之间的关联和应用，适合有一定基础的学生",
        "hard": "深度分析题，考察复杂场景下的推理和批判性思维，适合进阶学生"
    }
    varied_index = _stable_variant(question, 3)

    # ── 构建强制题型提示词 ──
    type_templates = {
        "choice": {
            "desc": "单选题（4个选项A/B/C/D，只有一个正确答案）",
            "format": '{"quiz": "题干", "options": {"A":"选项A","B":"选项B","C":"选项C","D":"选项D"}, "correct": "A", "keywords": ["关键词1","关键词2","关键词3"]}',
        },
        "fill": {
            "desc": "填空题（用____标记空缺处，可多个空）",
            "format": '{"quiz": "包含____的填空题题干", "blanks": ["答案1","答案2"], "keywords": ["关键词1","关键词2","关键词3"]}',
        },
        "true_false": {
            "desc": "判断题（一句陈述，判断对错）",
            "format": '{"quiz": "判断正误的陈述句", "correct": true, "explanation": "原因", "keywords": ["关键词1","关键词2","关键词3"]}',
        },
        "short_answer": {
            "desc": "简答题",
            "format": '{"quiz": "题目内容", "keywords": ["关键词1","关键词2","关键词3"]}',
        },
    }
    if question_type == "varied":
        actual_type = ["choice", "fill", "short_answer"][varied_index]
    else:
        actual_type = question_type
    tmpl = type_templates.get(actual_type, type_templates["short_answer"])

    try:
        request_key = _api_key(api_key)
        if not request_key:
            raise RuntimeError("未配置 DeepSeek API Key")
        system_msg = (
            f"你是一名出题老师。你必须严格按照指定JSON格式出题，不得输出其他内容。"
            f"题型：{tmpl['desc']}。难度：{difficulty_guide.get(difficulty, '中等')}。"
        )
        user_msg = (
            f"主题：「{question}」\n"
            f"知识点：{working_context[:600] if working_context else '无'}\n"
            f"请用此JSON格式回复（必须包含所有字段）：{tmpl['format']}"
        )
        resp = httpx.post(
            f"{DEEPSEEK_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {request_key}"},
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg}
                ],
                "temperature": 0.5,
                "max_tokens": 500,
                "response_format": {"type": "json_object"}
            },
            timeout=25
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        quiz = parsed.get("quiz", "")
        keywords = parsed.get("keywords", [])
        q_type = actual_type
        extra = {}
        if q_type == "choice":
            extra["options"] = parsed.get("options", {})
            extra["correct"] = parsed.get("correct", "")
            # 如果 LLM 没返回选项，用关键词构造选项
            if not extra["options"] or len(extra["options"]) < 3:
                fake_opts = {"A": keywords[0] if len(keywords) > 0 else "正确",
                             "B": keywords[1] if len(keywords) > 1 else "错误",
                             "C": keywords[2] if len(keywords) > 2 else "以上都是",
                             "D": "以上都不对"}
                extra["options"] = fake_opts
                extra["correct"] = "A"
        elif q_type == "fill":
            extra["blanks"] = parsed.get("blanks", keywords[:2] if keywords else ["___"])
        elif q_type == "true_false":
            extra["correct"] = parsed.get("correct", False)
            extra["explanation"] = parsed.get("explanation", "")
        if quiz and keywords:
            return working_context, keywords, quiz, q_type, extra
    except Exception as e:
        print(f"[QUIZ] LLM出题失败，降级到词频：{e}")

    # ── 降级方案（LLM失败时）—— 尊重用户选择的题型 ──
    keywords = _extract_keywords(working_context)
    if not keywords:
        keywords = _extract_keywords(question)
    if not keywords:
        quiz = f"请简述你对「{question}」的理解。"
        return working_context, [], quiz, "short_answer", {}

    fallback_type = question_type if question_type != "varied" else "short_answer"
    extra = {}
    if fallback_type == "choice":
        kw_list = keywords[:4] if len(keywords) >= 4 else (keywords + ["以上都是", "以上都不对"])[:4]
        options = {}
        for i, label in enumerate(["A", "B", "C", "D"]):
            options[label] = kw_list[i] if i < len(kw_list) else f"选项{label}"
        extra["options"] = options
        extra["correct"] = "A"
        quiz = f"关于「{question}」，以下哪项描述最准确？"
    elif fallback_type == "fill":
        extra["blanks"] = keywords[:2]
        kw_str = "____、____"
        quiz = f"请填写关于「{question}」的关键术语：{kw_str}"
    elif fallback_type == "true_false":
        extra["correct"] = True
        extra["explanation"] = f"核心概念：{keywords[0]}"
        quiz = f"判断：「{question}」的核心概念是{keywords[0]}。"
    else:
        quiz = "请用一句话解释以下关键词并至少覆盖其中两个：" + "、".join(keywords[:3])
    return working_context, keywords[:4], quiz, fallback_type, extra

def _grade_answer_llm(
    question: str,
    answer: str,
    keywords: list,
    reference_answer: Optional[str] = None,
    api_key: Optional[str] = None,
    min_hit: int = 1,
) -> tuple:
    kw_str = "、".join(keywords) if keywords else "无"
    prompt = f"""你是一名严格但公正的老师，请判断学生的回答是否正确。

题目：{question}
参考知识点关键词：{kw_str}
参考答案：{reference_answer or '无'}
学生回答：{answer}

请用JSON格式回复，不要有其他内容：
{{
  "passed": true或false,
  "matched_concepts": ["命中的概念1", "命中的概念2"],
  "feedback": "一句话点评，指出对的地方和缺少的地方"
}}"""
    try:
        request_key = _api_key(api_key)
        if not request_key:
            raise RuntimeError("未配置 DeepSeek API Key")
        resp = httpx.post(
            f"{DEEPSEEK_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {request_key}"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 300,
                "response_format": {"type": "json_object"}
            },
            timeout=20
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        passed = parsed.get("passed", False)
        hits = parsed.get("matched_concepts", [])
        feedback = parsed.get("feedback", "")
        result = "校验通过" if passed else "校验未通过"
        return result, hits, feedback
    except Exception:
        # 降级到关键词匹配
        lowered = answer.casefold()
        hits = [k for k in (keywords or []) if str(k).casefold() in lowered]
        passed = len(hits) >= max(1, min_hit)
        return (
            "校验通过" if passed else "校验未通过",
            hits,
            "AI评分暂时不可用，已降级到关键词匹配。",
        )


LEARNING_DB_PATH = _runtime_path("LITETUTOR_LEARNING_DB", "user_learning_db.json")
UPLOAD_DIR = _runtime_path("LITETUTOR_UPLOAD_DIR", "uploads")
LEARNING_DB_LOCK = Lock()
tutor_sessions: Dict[str, Dict[str, Any]] = {}

def _load_learning_db() -> dict:
    if LEARNING_DB_PATH.exists():
        try:
            return json.loads(LEARNING_DB_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save_learning_db(db: dict):
    LEARNING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = LEARNING_DB_PATH.with_suffix(LEARNING_DB_PATH.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temp_path.replace(LEARNING_DB_PATH)


def _record_learning(session_id: str, record: dict) -> None:
    with LEARNING_DB_LOCK:
        learning_db.setdefault(session_id, []).append(record)
        _save_learning_db(learning_db)

learning_db = _load_learning_db()

print("Waking up Right Brain (ChromaDB)...")
rag_db = LocalRAGKnowledgeBase(
    db_path=_runtime_path("LITETUTOR_RAG_DB", "chroma_db")
)

# 启动时自动导入本地知识文件
_auto_files = ["data_structure_notes.txt", "math.md"]
for _f in _auto_files:
    _path = BASE_DIR / _f
    if _path.exists():
        try:
            # 尝试utf-8，失败则用gbk
            try:
                _text = _path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                _text = _path.read_text(encoding="gbk")
            rag_db.add_document(_text, source=_f)
            print(f"[AUTO-IMPORT] {_f} 已导入知识库")
        except Exception as _e:
            print(f"[AUTO-IMPORT] {_f} 导入失败：{_e}")

class TaskRequest(BaseModel):
    code: str = Field(min_length=1, max_length=10_000)
    language: Literal["python"] = "python"
    timeout: int = Field(default=10, ge=1, le=10)

@app.post("/solve")
async def receive_task(request: TaskRequest):
    if not ALLOW_CODE_EXECUTION:
        return {
            "status": "disabled",
            "message": "本地代码执行默认关闭。仅在可信环境中设置 LITETUTOR_ENABLE_CODE_EXECUTION=true 后启用。"
        }
    try:
        with tempfile.TemporaryDirectory(prefix="litetutor_exec_") as work_dir:
            safe_env = {
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                "TEMP": work_dir,
                "TMP": work_dir,
                "PYTHONIOENCODING": "utf-8",
            }
            result = subprocess.run(
                [sys.executable, "-I", "-S", "-c", request.code],
                capture_output=True,
                text=True,
                timeout=request.timeout,
                cwd=work_dir,
                env=safe_env,
            )
        return {
            "status": "success" if result.returncode == 0 else "failed",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    mode: Literal["hybrid", "vector"] = "hybrid"
    n_results: int = Field(default=2, ge=1, le=10)

@app.post("/search")
async def search_knowledge(req: SearchRequest):
    print("\n" + "="*60)
    print(f"[SEARCH RECEIVED] Query: {req.query}")
    try:
        documents, distances, metadatas = rag_db.query_knowledge_chunks_with_scores(
            req.query, n_results=req.n_results
        )
        if req.mode.lower() != "vector":
            hybrid_results = rag_db.query_knowledge_hybrid_with_metadata(
                req.query, n_results=req.n_results
            )
            if hybrid_results:
                documents = [item[0] for item in hybrid_results]
                metadatas = [item[1] for item in hybrid_results]
        confidence = 0.0
        if distances:
            confidence = 1.0 / (1.0 + distances[0])
        if req.mode.lower() != "vector":
            confidence = max(confidence, rag_db.keyword_confidence(req.query))
        threshold = float(os.getenv("RAG_CONF_THRESHOLD", "0.35"))
        fallback_required = (not documents) or (confidence < threshold)
        if fallback_required:
            return {
                "status": "success",
                "context": "",
                "sources": [],
                "fallback_required": True,
                "confidence": confidence
            }
        retrieved_context = "\n---\n".join(documents)
        print(f"[SEARCH RESULT] Found {len(retrieved_context)} characters of context.")
        sources = []
        for metadata in metadatas:
            source = metadata.get("source", "unknown")
            page = metadata.get("page")
            item = {"source": source}
            if page:
                item["page"] = page
            if item not in sources:
                sources.append(item)
        return {
            "status": "success", 
            "context": retrieved_context,
            "sources": sources,
            "fallback_required": False,
            "confidence": confidence
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

class QuizRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    context: Optional[str] = Field(default=None, max_length=10_000)
    n_results: int = Field(default=2, ge=1, le=10)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    question_type: Literal["varied", "choice", "fill", "short_answer", "true_false"] = "varied"

@app.post("/quiz")
async def generate_quiz(
    req: QuizRequest,
    x_api_key: Optional[str] = Header(None, alias="X-LiteTutor-API-Key"),
):
    try:
        context, keywords, quiz, q_type, extra = _build_quiz(
            req.question, req.context, req.n_results,
            difficulty=req.difficulty, question_type=req.question_type,
            api_key=x_api_key,
        )
        return {
            "status": "success",
            "quiz": quiz,
            "keywords": keywords,
            "context": context,
            "question_type": q_type,
            **extra
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

class GradeRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=10_000)
    keywords: Optional[List[str]] = None
    min_hit: int = Field(default=1, ge=1, le=20)
    session_id: Optional[str] = Field(default="default", max_length=128)
    question: Optional[str] = Field(default="", max_length=5_000)
    question_type: Literal["choice", "fill", "short_answer", "true_false"] = "short_answer"
    expected_answer: Optional[Any] = None
    reference_answer: Optional[str] = None

@app.post("/grade")
async def grade_answer(
    req: GradeRequest,
    x_api_key: Optional[str] = Header(None, alias="X-LiteTutor-API-Key"),
):
    try:
        structured_result = grade_structured_answer(
            req.question_type, req.answer, req.expected_answer
        )
        if structured_result is not None:
            result, hits, feedback = structured_result
        else:
            result, hits, feedback = _grade_answer_llm(
                question=req.question or "",
                answer=req.answer,
                keywords=req.keywords or [],
                reference_answer=req.reference_answer,
                api_key=x_api_key,
                min_hit=req.min_hit,
            )
        record = {
            "timestamp": datetime.now().isoformat(),
            "question": req.question or "",
            "keywords": req.keywords or [],
            "answer": req.answer,
            "result": result,
            "hits": hits,
            "feedback": feedback,
            "question_type": req.question_type,
        }
        sid = req.session_id or "default"
        _record_learning(sid, record)
        return {"status": "success", "result": result, "matched_keywords": hits, "feedback": feedback}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/tools")
async def list_tools():
    public_url = os.getenv("EDGE_PUBLIC_URL", "http://127.0.0.1:8000").strip()
    tools = get_tool_schemas(public_url, include_compute=ALLOW_CODE_EXECUTION)
    return {"status": "success", "tools": tools}

class TutorRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, max_length=128)
    user_input: str = Field(min_length=1, max_length=5_000)
    reset: bool = False

@app.post("/tutor")
async def tutor_fsm(
    req: TutorRequest,
    x_api_key: Optional[str] = Header(None, alias="X-LiteTutor-API-Key"),
):
    session_id = req.session_id or str(uuid.uuid4())
    state = tutor_sessions.get(session_id)
    if req.reset or not state or state.get("stage") == "complete":
        state = {
            "stage": "explain",
            "question": req.user_input.strip(),
            "context": "",
            "keywords": [],
            "quiz": {},
        }
        tutor_sessions[session_id] = state
        response = (
            f"我先了解一下你对「{state['question']}」的掌握情况。"
            "你目前已经知道什么，或者具体卡在哪里？"
        )
        return {"status": "success", "session_id": session_id, "stage": "diagnose", "response": response}

    stage = state["stage"]
    if stage == "explain":
        learner_state = req.user_input.strip()
        context = rag_db.query_knowledge_hybrid(state["question"], n_results=2)
        keywords = _extract_keywords(context or state["question"])
        state["context"] = context
        state["keywords"] = keywords
        request_key = _api_key(x_api_key)
        response = ""
        if request_key:
            prompt = f"""你是一名循序渐进的导师。请根据学生的当前理解，用简洁中文进行启发式讲解。

学习主题：{state['question']}
学生自述：{learner_state}
课件资料：{context[:1800]}

要求：先回应学生的卡点，再用一个直观例子讲清核心概念，最后给出一个自检问题。不要直接堆砌课件原文。"""
            try:
                resp = httpx.post(
                    f"{DEEPSEEK_BASE}/chat/completions",
                    headers={"Authorization": f"Bearer {request_key}"},
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.4,
                        "max_tokens": 700,
                    },
                    timeout=25,
                )
                resp.raise_for_status()
                response = resp.json()["choices"][0]["message"]["content"]
            except Exception:
                response = ""
        if not response:
            if context:
                response = f"结合你刚才的卡点，可以先抓住这些核心内容：\n\n{context}"
            else:
                response = "本地知识库中暂未找到相关课件内容，请先上传资料或换一个更具体的主题。"
        response += "\n\n理解后回复“继续”，我会根据这个知识点出一道检查题。"
        state["stage"] = "quiz"
        return {"status": "success", "session_id": session_id, "stage": "explain", "response": response}

    if stage == "quiz":
        _, keywords, prompt, q_type, extra = _build_quiz(
            state["question"], state.get("context", ""), 2,
            difficulty="medium", question_type="varied", api_key=x_api_key,
        )
        state["keywords"] = keywords
        state["quiz"] = {"question": prompt, "question_type": q_type, **extra}
        state["stage"] = "validate"
        option_text = ""
        if q_type == "choice":
            option_text = "\n" + "\n".join(
                f"{key}. {value}" for key, value in extra.get("options", {}).items()
            )
        return {
            "status": "success", "session_id": session_id, "stage": "quiz",
            "response": prompt + option_text, "question_type": q_type,
        }

    if stage == "validate":
        keywords = state.get("keywords", [])
        answer = req.user_input.strip()
        quiz = state.get("quiz", {})
        expected = quiz.get("blanks") if quiz.get("question_type") == "fill" else quiz.get("correct")
        structured_result = grade_structured_answer(
            quiz.get("question_type", "short_answer"), answer, expected
        )
        if structured_result is not None:
            result, hits, feedback = structured_result
        else:
            result, hits, feedback = _grade_answer_llm(
                question=quiz.get("question", state.get("question", "")),
                answer=answer,
                keywords=keywords,
                api_key=x_api_key,
            )
        record = {
            "timestamp": datetime.now().isoformat(),
            "question": quiz.get("question", state.get("question", "")),
            "keywords": keywords,
            "answer": answer,
            "result": result,
            "hits": hits,
            "feedback": feedback,
            "question_type": quiz.get("question_type", "short_answer"),
        }
        _record_learning(session_id, record)
        if result == "校验通过":
            response = f"{result}。{feedback}\n\n这一轮完成了。直接输入新主题即可开始下一轮。"
            state["stage"] = "complete"
        else:
            response = f"{result}。{feedback}\n\n我会降低一点难度重新检查。回复“继续”获取补救题。"
            state["stage"] = "remediate"
        return {
            "status": "success", "session_id": session_id, "stage": "validate",
            "response": response, "matched_keywords": hits,
        }

    if stage == "remediate":
        _, keywords, prompt, q_type, extra = _build_quiz(
            state["question"], state.get("context", ""), 2,
            difficulty="easy", question_type="choice", api_key=x_api_key,
        )
        state["keywords"] = keywords
        state["quiz"] = {"question": prompt, "question_type": q_type, **extra}
        state["stage"] = "validate"
        option_text = "\n" + "\n".join(
            f"{key}. {value}" for key, value in extra.get("options", {}).items()
        )
        return {
            "status": "success", "session_id": session_id, "stage": "remediate",
            "response": "我们换一道更基础的题：\n\n" + prompt + option_text,
            "question_type": q_type,
        }

    return {"status": "error", "session_id": session_id, "message": "未知教学状态"}

@app.get("/learning_stats")
async def get_learning_stats(session_id: str = Query(default="default", max_length=128)):
    records = learning_db.get(session_id, [])
    return {"status": "success", "records": records}

@app.get("/all_sessions")
async def get_all_sessions():
    return {"status": "success", "sessions": list(learning_db.keys())}

@app.post("/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """上传PDF，自动解析文本并加入知识库"""
    original_name = Path(file.filename or "upload.pdf").name
    if Path(original_name).suffix.lower() != ".pdf":
        return {"status": "error", "message": "只支持PDF文件"}
    try:
        # 读取上传的PDF内容
        contents = await file.read()
        max_mb = max(1, int(os.getenv("LITETUTOR_MAX_PDF_MB", "20")))
        max_bytes = max_mb * 1024 * 1024
        if len(contents) > max_bytes:
            return {"status": "error", "message": f"PDF文件过大，请上传{max_mb}MB以内的文件"}
        
        all_text = []
        with fitz.open(stream=contents, filetype="pdf") as doc:
            for page_num, page in enumerate(doc):
                text = page.get_text().strip()
                if text:
                    all_text.append(f"【第{page_num+1}页】\n{text}")
        
        if not all_text:
            return {"status": "error", "message": "PDF中没有可提取的文字（可能是扫描件）"}
        
        full_text = "\n\n".join(all_text)
        
        # 存到本地txt备份
        safe_name = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "_", Path(original_name).stem)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        txt_path = UPLOAD_DIR / f"{safe_name}_extracted.txt"
        txt_path.write_text(full_text, encoding="utf-8")
        
        # 加入RAG知识库
        added = rag_db.add_document(full_text, source=original_name)
        if not added:
            return {
                "status": "error",
                "message": "该文档已存在于知识库中，无需重复导入"
            }
        
        return {
            "status": "success",
            "filename": original_name,
            "pages": len(all_text),
            "chars": len(full_text),
            "message": f"成功导入{len(all_text)}页内容到知识库"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/knowledge_sources")
async def list_knowledge_sources():
    """列出当前知识库里有哪些文档"""
    try:
        sources = rag_db.list_sources()
        return {"status": "success", "sources": sources}
    except Exception:
        return {"status": "success", "sources": ["（知识库不支持来源列表）"]}
    
@app.delete("/knowledge_source/{source_name}")
async def delete_knowledge_source(source_name: str):
    """删除知识库中指定来源的所有chunk"""
    try:
        results = rag_db.collection.get(include=["metadatas"])
        ids_to_delete = [
            results["ids"][i]
            for i, m in enumerate(results["metadatas"])
            if m.get("source") == source_name
        ]
        if not ids_to_delete:
            return {"status": "error", "message": "未找到该文档"}
        rag_db.collection.delete(ids=ids_to_delete)
        return {"status": "success", "message": f"已删除 {len(ids_to_delete)} 个chunk，来源：{source_name}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("LITETUTOR_HOST", "127.0.0.1"),
        port=int(os.getenv("LITETUTOR_PORT", "8000")),
    )
