import os
import subprocess
import re
import uuid
from collections import Counter
from typing import Optional, Dict, Any, List
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import json
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, File
import fitz  # pymupdf
import tempfile


from rag_builder import LocalRAGKnowledgeBase
from edge_tool import get_tool_schemas

class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"

app = FastAPI(title="LiteTutor Edge Node", default_response_class=UTF8JSONResponse)

def _tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", text.lower()) if len(t) > 1]

def _extract_keywords(text: str, limit: int = 4) -> List[str]:
    tokens = _tokenize(text)
    if not tokens:
        return []
    counts = Counter(tokens)
    return [w for w, _ in counts.most_common(limit)]

def _build_quiz(question: str, context: Optional[str] = None, n_results: int = 2,
                difficulty: str = "medium", question_type: str = "varied"):
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
    diff_desc = difficulty_guide.get(difficulty, difficulty_guide["medium"])

    type_guide = {
        "choice": "出单选题，4个选项(A/B/C/D)，正确选项需明确标注",
        "fill": "出填空题，用____标记空缺处，考察关键术语或核心概念",
        "short_answer": "出简答题，要求用一段话阐述概念或原理",
        "true_false": "出判断题，给出一个陈述让学生判断对错并简述理由",
        "varied": f"从以下题型中随机选择一种：{'选择题' if hash(question)%3==0 else '填空题' if hash(question)%3==1 else '简答题'}"
    }
    type_desc = type_guide.get(question_type, type_guide["varied"])

    # 根据题型决定JSON输出格式
    if question_type == "choice" or (question_type == "varied" and hash(question) % 3 == 0):
        output_format = """{
      "question_type": "choice",
      "quiz": "题目内容（题干）",
      "options": {"A": "选项A内容", "B": "选项B内容", "C": "选项C内容", "D": "选项D内容"},
      "correct": "A",
      "keywords": ["关键词1", "关键词2", "关键词3"]
    }"""
    elif question_type == "fill" or (question_type == "varied" and hash(question) % 3 == 1):
        output_format = """{
      "question_type": "fill",
      "quiz": "包含____的填空题题干（可以有多个____）",
      "blanks": ["答案1", "答案2"],
      "keywords": ["关键词1", "关键词2", "关键词3"]
    }"""
    elif question_type == "true_false":
        output_format = """{
      "question_type": "true_false",
      "quiz": "判断正误的陈述句",
      "correct": true或false,
      "explanation": "正确/错误的原因简述",
      "keywords": ["关键词1", "关键词2", "关键词3"]
    }"""
    else:
        output_format = """{
      "question_type": "short_answer",
      "quiz": "题目内容",
      "keywords": ["关键词1", "关键词2", "关键词3"]
    }"""

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
        actual_type = ["choice", "fill", "short_answer"][hash(question) % 3]
    else:
        actual_type = question_type
    tmpl = type_templates.get(actual_type, type_templates["short_answer"])

    try:
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
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
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

import httpx

DEEPSEEK_API_KEY = ""
DEEPSEEK_BASE = "https://api.deepseek.com/v1"

def _grade_answer(answer: str, keywords: list, min_hit: int = 1):
    """保留原接口兼容性"""
    hits = [k for k in (keywords or []) if k in answer]
    result = "校验通过" if len(hits) >= min_hit else "校验未通过"
    return result, hits

# ✅ LLM语义评分（主力）
def _grade_answer_llm(question: str, answer: str, keywords: list) -> tuple:
    kw_str = "、".join(keywords) if keywords else "无"
    prompt = f"""你是一名严格但公正的老师，请判断学生的回答是否正确。

题目：{question}
参考知识点关键词：{kw_str}
学生回答：{answer}

请用JSON格式回复，不要有其他内容：
{{
  "passed": true或false,
  "matched_concepts": ["命中的概念1", "命中的概念2"],
  "feedback": "一句话点评，指出对的地方和缺少的地方"
}}"""
    try:
        resp = httpx.post(
            f"{DEEPSEEK_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 300,
                "response_format": {"type": "json_object"}
            },
            timeout=20
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        passed = parsed.get("passed", False)
        hits = parsed.get("matched_concepts", [])
        feedback = parsed.get("feedback", "")
        result = "校验通过" if passed else "校验未通过"
        return result, hits, feedback
    except Exception as e:
        # 降级到关键词匹配
        hits = [k for k in (keywords or []) if k in answer.lower()]
        result = "校验通过" if hits else "校验未通过"
        return result, hits, f"（AI评分暂时不可用，已降级到关键词匹配）"


# ✅ 保留原版作为降级备用（改名加下划线前缀）
def _grade_answer(answer: str, keywords: Optional[List[str]] = None, min_hit: int = 1):
    clean_answer = answer.strip()
    lowered = clean_answer.lower()
    keyword_list = keywords or []
    hits = [k for k in keyword_list if k in lowered]
    threshold = max(1, min_hit)
    if keyword_list and len(hits) >= threshold:
        result = "校验通过"
    elif not keyword_list and len(clean_answer) >= 6:
        result = "校验通过"
    else:
        result = "校验未通过"
    return result, hits


LEARNING_DB_PATH = Path("learning_db.json")
tutor_sessions: Dict[str, Dict[str, Any]] = {}

def _load_learning_db() -> dict:
    if LEARNING_DB_PATH.exists():
        try:
            return json.loads(LEARNING_DB_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save_learning_db(db: dict):
    LEARNING_DB_PATH.write_text(
        json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8"
    )

learning_db = _load_learning_db()

print("Waking up Right Brain (ChromaDB)...")
rag_db = LocalRAGKnowledgeBase()

# 启动时自动导入本地知识文件
import pathlib
_auto_files = ["data_structure_notes.txt", "math.md"]
for _f in _auto_files:
    _path = pathlib.Path(_f)
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
    task_instruction: Optional[str] = None
    code: Optional[str] = None
    language: str = "python"
    timeout: int = 20

@app.post("/solve")
async def receive_task(request: TaskRequest):
    if request.code and request.code.strip():
        if request.language.lower() != "python":
            return {"status": "error", "message": "Only python is supported for code execution."}
        try:
            result = subprocess.run(
                ["python", "-c", request.code],
                capture_output=True,
                text=True,
                timeout=request.timeout
            )
            return {
                "status": "success" if result.returncode == 0 else "failed",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    if request.task_instruction and request.task_instruction.strip():
        instruction = request.task_instruction
        print("\n" + "="*60)
        print(f"[TASK RECEIVED] Instruction: {instruction}")
        try:
            print("Waking up OpenCode Native UI (Fire-and-Forget Mode)...")
            full_command = f'opencode --prompt "{instruction}"'
            subprocess.Popen(full_command, shell=True)
            return {
                "status": "success", 
                "solution": "[Task dispatched successfully. Execution output is rendering natively on the Edge Node physical screen.]"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return {"status": "error", "message": "Either task_instruction or code must be provided."}

class SearchRequest(BaseModel):
    query: str
    mode: str = "hybrid"
    n_results: int = 2

@app.post("/search")
async def search_knowledge(req: SearchRequest):
    print("\n" + "="*60)
    print(f"[SEARCH RECEIVED] Query: {req.query}")
    try:
        documents, distances = rag_db.query_knowledge_chunks_with_scores(req.query, n_results=req.n_results)
        confidence = 0.0
        if distances:
            confidence = 1.0 / (1.0 + distances[0])
        threshold = float(os.getenv("RAG_CONF_THRESHOLD", "0.35"))
        fallback_required = (not documents) or (confidence < threshold)
        if fallback_required:
            return {
                "status": "success",
                "context": "",
                "fallback_required": True,
                "confidence": confidence
            }
        if req.mode.lower() == "vector":
            retrieved_context = "\n---\n".join(documents)
        else:
            retrieved_context = rag_db.query_knowledge_hybrid(req.query, n_results=req.n_results)
        print(f"[SEARCH RESULT] Found {len(retrieved_context)} characters of context.")
        return {
            "status": "success", 
            "context": retrieved_context,
            "fallback_required": False,
            "confidence": confidence
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

class QuizRequest(BaseModel):
    question: str
    context: Optional[str] = None
    n_results: int = 2
    difficulty: str = "medium"      # easy | medium | hard
    question_type: str = "varied"   # varied | choice | fill | short_answer | true_false

@app.post("/quiz")
async def generate_quiz(req: QuizRequest):
    try:
        context, keywords, quiz, q_type, extra = _build_quiz(
            req.question, req.context, req.n_results,
            difficulty=req.difficulty, question_type=req.question_type
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
    answer: str
    keywords: Optional[List[str]] = None
    min_hit: int = 1
    session_id: Optional[str] = "default"
    question: Optional[str] = ""

@app.post("/grade")
async def grade_answer(req: GradeRequest):
    try:
        result, hits, feedback = _grade_answer_llm(
            question=req.question or "",
            answer=req.answer,
            keywords=req.keywords or []
        )
        record = {
            "timestamp": datetime.now().isoformat(),
            "question": req.question or "",
            "keywords": req.keywords or [],
            "answer": req.answer,
            "result": result,
            "hits": hits,
            "feedback": feedback
        }
        sid = req.session_id or "default"
        if sid not in learning_db:
            learning_db[sid] = []
        learning_db[sid].append(record)
        _save_learning_db(learning_db)
        return {"status": "success", "result": result, "matched_keywords": hits, "feedback": feedback}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/tools")
async def list_tools():
    public_url = os.getenv("EDGE_PUBLIC_URL", "http://127.0.0.1:8000").strip()
    tools = get_tool_schemas(public_url)
    return {"status": "success", "tools": tools}

class TutorRequest(BaseModel):
    session_id: Optional[str] = None
    user_input: str

@app.post("/tutor")
async def tutor_fsm(req: TutorRequest):
    session_id = req.session_id or str(uuid.uuid4())
    state = tutor_sessions.get(session_id)
    if not state:
        state = {
            "stage": "diagnose",
            "question": req.user_input.strip(),
            "context": "",
            "keywords": []
        }
        tutor_sessions[session_id] = state

    stage = state["stage"]
    if stage == "diagnose":
        response = (
            f"我先做诊断：你正在处理的问题是「{state['question']}」。"
            "请补充你目前的解题进度或卡住点。"
        )
        state["stage"] = "explain"
        return {"status": "success", "session_id": session_id, "stage": "diagnose", "response": response}

    if stage == "explain":
        context, keywords, _, _, _ = _build_quiz(state["question"], None, 2)
        state["context"] = context
        state["keywords"] = keywords
        response = (
            "启发讲解如下：\n\n"
            f"{context}\n\n"
            "如果理解了，请回答「继续测验」。"
        )
        state["stage"] = "quiz"
        return {"status": "success", "session_id": session_id, "stage": "explain", "response": response}

    if stage == "quiz":
        _, keywords, prompt, _, _ = _build_quiz(state["question"], state.get("context", ""), 2)
        state["keywords"] = keywords
        state["stage"] = "validate"
        return {"status": "success", "session_id": session_id, "stage": "quiz", "response": prompt}

    if stage == "validate":
        keywords = state.get("keywords", [])
        answer = req.user_input.strip()
        result, hits, feedback = _grade_answer_llm(
            question=state.get("question", ""),
            answer=answer,
            keywords=keywords
        )
        # 记录到学习数据库
        record = {
            "timestamp": datetime.now().isoformat(),
            "question": state.get("question", ""),
            "keywords": keywords,
            "answer": answer,
            "result": result,
            "hits": hits,
            "feedback": feedback
        }
        sid = session_id
        if sid not in learning_db:
            learning_db[sid] = []
        learning_db[sid].append(record)
        _save_learning_db(learning_db)
        response = f"{result}。{feedback}\n\n如果需要，我可以继续补充讲解或出新题。"
        state["stage"] = "complete"
        return {"status": "success", "session_id": session_id, "stage": "validate", "response": response, "matched_keywords": hits}

    response = "本轮已完成。如需继续，请提交新问题。"
    return {"status": "success", "session_id": session_id, "stage": "complete", "response": response}

@app.get("/learning_stats")
async def get_learning_stats(session_id: str = "default"):
    records = learning_db.get(session_id, [])
    return {"status": "success", "records": records}

@app.get("/all_sessions")
async def get_all_sessions():
    return {"status": "success", "sessions": list(learning_db.keys())}

@app.post("/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """上传PDF，自动解析文本并加入知识库"""
    if not file.filename.endswith(".pdf"):
        return {"status": "error", "message": "只支持PDF文件"}
    try:
        # 读取上传的PDF内容
        contents = await file.read()
        
        # 用临时文件解析
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        # 用pymupdf提取文字
        doc = fitz.open(tmp_path)
        all_text = []
        for page_num, page in enumerate(doc):
            text = page.get_text().strip()
            if text:
                all_text.append(f"【第{page_num+1}页】\n{text}")
        doc.close()
        os.unlink(tmp_path)
        
        if not all_text:
            return {"status": "error", "message": "PDF中没有可提取的文字（可能是扫描件）"}
        
        full_text = "\n\n".join(all_text)
        
        # 存到本地txt备份
        safe_name = file.filename.replace(".pdf", "").replace(" ", "_")
        txt_path = Path(f"{safe_name}_extracted.txt")
        txt_path.write_text(full_text, encoding="utf-8")
        
        # 加入RAG知识库
        added = rag_db.add_document(full_text, source=file.filename)
        if not added:
            return {
                "status": "error",
                "message": f"该文档已存在于知识库中，无需重复导入"
            }
        
        return {
            "status": "success",
            "filename": file.filename,
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
