# Lite-Tutor 自适应智能辅导系统

Lite-Tutor 把课件检索、针对性讲解、测验、判分和学习记录串成一条本地教学闭环：

```text
上传 PDF → 课件检索（带来源）→ 诊断当前卡点 → 针对性讲解
→ 自动测验 → 客观题确定性判分 / 简答题语义判分 → 错题补救
```

## 环境要求

- Python 3.10 及以上
- Windows 可使用一键启动脚本；macOS/Linux 可分别启动后端和前端

## 安装与启动

```bash
pip install -r requirements.txt
```

Windows 下双击 `start_litetutor.bat`。其他系统可分别运行：

```bash
python server.py
streamlit run app.py --server.address 127.0.0.1
```

浏览器访问 `http://localhost:8501`。后端默认只监听 `127.0.0.1:8000`。

## API Key

可以在页面左侧临时填写 API Key；前端只会将它转发给本机后端，不会写入项目文件。也可以在启动后端前设置环境变量：

```powershell
$env:DEEPSEEK_API_KEY="你的 Key"
python server.py
```

不要把真实 Key 写入源码、`.env.example` 或提交到 Git。

## 三种模式

- **Lite**：普通云端对话，不主动检索本地课件。
- **Standard**：先检索本地课件，并在回答末尾显示文件名和页码。
- **Pro**：在 Standard 基础上开放知识检索、出题和评分工具。

在「对话学习」中开启“自适应教学闭环”后，系统会按“诊断 → 讲解 → 测验 → 补救”的状态推进，并把答题结果写入掌握曲线与错题本。

## 本地数据

以下运行数据均被 Git 忽略：

- `chroma_db/`：本地向量数据库
- `user_learning_db.json`：真实学习记录
- `uploads/`：上传 PDF 后提取的文本
- `.env`：本地环境变量

仓库中的 `learning_db.json` 与 `fake_data.py` 仅用于生成界面演示数据，不会与真实学习记录混用。

## 安全说明

- 后端默认只允许本机访问。
- `/solve` 默认关闭，而且只接受受限的 Python 子进程；它仍不等同于完整安全沙箱。
- 只有在本机可信环境确实需要演示时，才设置 `LITETUTOR_ENABLE_CODE_EXECUTION=true`。
- 如果将后端暴露到局域网或公网，应先增加独立身份验证、TLS 和访问控制。

更多配置见 `.env.example`。

## 验证

单元测试：

```bash
python -m unittest discover -s tests -v
```

启动后端后，可在 PowerShell 中运行端到端检查：

```powershell
.\check_all.ps1
```

## 主要文件

- `app.py`：Streamlit 前端
- `server.py`：FastAPI 后端与教学状态机
- `assessment.py`：客观题统一判分逻辑
- `rag_builder.py`：稳定离线向量与混合检索
- `edge_tool.py`：Function Calling 工具定义
- `start_litetutor.bat`：Windows 一键启动
