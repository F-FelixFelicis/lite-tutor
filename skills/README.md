# Lite-Tutor 智能辅导系统

## 环境要求
- Python 3.10 及以上
- Windows 系统

## 安装步骤

### 1. 安装依赖
打开终端，进入项目文件夹，运行：
```
pip install -r requirements.txt
```

### 2. 填入 API Key
打开 `server.py`，找到第几行：
```python
DEEPSEEK_API_KEY = "填入你的key"
```
将引号内替换为你自己的 DeepSeek API Key。

### 3. 启动系统
双击 `start_litetutor.bat` 即可自动启动前后端。

浏览器会自动打开，或手动访问：http://localhost:8501

### 4. 使用说明
- 左侧边栏填入 OpenClaw Base URL（直接用 DeepSeek 官方填 `https://api.deepseek.com/v1`）
- 左侧边栏填入 API Key
- 上传课件 PDF 到知识库
- 在「测验」Tab 输入主题开始练习
- 在「掌握曲线」「错题本」「思维导图」查看学习情况

## 文件说明
- `app.py` — 前端界面
- `server.py` — 后端服务
- `rag_builder.py` — 知识库模块
- `edge_tool.py` — 工具模块
- `start_litetutor.bat` — 一键启动脚本
