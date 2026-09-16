# Lite-Tutor

面向个性化教学的轻量级自适应智能辅导系统。Lite-Tutor 将本地课件检索、针对性讲解、自动测验、确定性判分和学习记录连接成完整教学闭环。

## 主要能力

- 上传 PDF 课件并建立本地知识库
- 混合检索课件内容，并显示文件名与页码来源
- 诊断 → 讲解 → 测验 → 补救的自适应教学流程
- 选择、判断、填空题确定性判分
- 简答题语义评分及离线关键词降级
- 掌握曲线、错题本和知识点思维导图
- API Key 仅在本机转发，不写入项目文件

## 快速开始

```bash
cd skills
pip install -r requirements.txt
python server.py
```

另开一个终端启动界面：

```bash
cd skills
streamlit run app.py --server.address 127.0.0.1
```

Windows 用户也可以双击 `skills/start_litetutor.bat`。

完整配置、运行模式、安全边界和验证方法见 [使用说明](skills/README.md)。

## 验证状态

- Python 静态检查通过
- 7 项单元测试通过
- 后端接口端到端检查通过
- Streamlit 页面启动检查通过

真实学习记录、向量数据库、上传文件和本地密钥配置均被 Git 忽略。
