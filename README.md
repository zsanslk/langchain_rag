# 企业级智能文档管理与 RAG 问答系统 (v1.0)

本项目是一个基于前后端分离架构的企业级智能问答系统。系统以大型语言模型（LLM）为核心引擎，结合检索增强生成（RAG）架构，旨在解决企业内部私有文档的智能检索与高精度问答需求。

## 🌟 核心特性 (Core Features)

*   **全栈架构与 API 解耦**
    基于 Flask 框架构建 RESTful API，实现前端动态交互与底层大模型（Qwen-Plus）、检索服务的彻底解耦，系统具备高度的扩展性与可维护性。
*   **自动化文档处理流水线**
    构建了从长文本上传、清洗到结构化处理的高并发异步流水线。采用**递归字符动态切片算法**（512字符窗口 / 50字符重叠），保证非结构化文档在入库时的语义完整边界。
*   **高并发流式输出优化 (SSE)**
    针对大语言模型推理长耗时痛点，在网络通信层引入 **Server-Sent Events (SSE)** 长连接协议，实现真正的异步流式响应。经测试，**首字返回延迟 (TTFT) 稳定控制在 3 秒以内**，大幅优化前端请求拥塞与用户体验。
*   **双路混合检索与安全兜底架构**
    *   **混合检索**：在后端深度集成 FAISS 语义向量检索 (Dense) 与 BM25 稀疏检索 (Sparse) 算法。自建 70 例 Benchmark 测试表明，针对企业料号及专有名词，该混合架构将 Top-3 检索命中率提升至 **95.7%**。
    *   **安全防幻觉**：业务层设计并实现了基于相似度阈值的兜底拦截（熔断）机制。当检索置信度过低时，自动拦截 LLM 生成请求，防范系统产生无依据的“幻觉”回答。

## 🛠️ 技术栈 (Tech Stack)

*   **后端开发**：Python 3.10+, Flask, SQLAlchemy
*   **前端交互**：HTML/CSS, JavaScript, jQuery, AJAX
*   **AI 与 RAG 核心**：LangChain, FAISS (向量数据库), BM25, Qwen-Plus (阿里云百炼 API)
*   **数据通信**：RESTful API, Server-Sent Events (SSE)

## 📁 目录结构概览 (Directory Structure)

```text
langchain310_x/
├── app.py                  # Flask 后端应用主入口
├── config.py               # 环境变量与系统全局配置
├── routes/                 # RESTful API 路由模块 (认证、文档管理、聊天对话等)
├── models/                 # SQLAlchemy 数据库模型定义
├── templates/              # 前端 HTML 模板 (管理大盘、问答界面)
├── static/                 # 前端静态资源 (JS, CSS 交互脚本)
├── document_x/             # (被忽略) 存放原始业务文档的源目录
└── local_models/           # (被忽略) 存放本地 Embedding 预训练模型
```

## 🚀 部署与运行指南 (Quick Start)

### 1. 环境准备

推荐使用 Python 3.10 虚拟环境。

```bash
git clone <repository-url>
cd langchain310_x
python -m venv venv
# Windows: venv\Scripts\activate | Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
```

### 2. ⚠️ 核心数据与依赖目录说明（必看）

为保证代码仓库的轻量化，**在首次冷启动前，请务必完成以下操作：**

1.  **大模型权重加载 (`local_models/`)**
    该目录已被 Git 忽略。请在项目根目录手动创建 `local_models` 文件夹，并从 HuggingFace 或 ModelScope 下载本项目依赖的离线 Embedding 模型（如 `text2vec-base-chinese`）解压至该目录中。
2.  **知识库源文件 (`document_x/`)**
    此目录用于存放待向量化处理的私有文档源文件，已被忽略。启动系统后，请通过 Web 前端管理后台的“文档上传”功能上传企业文档，系统将自动创建对应目录并触发分片清洗任务。
3.  **本地向量索引 (`*.faiss`, `*.pkl`)**
    离线构建的高维向量索引文件已被忽略。当在管理后台重新上传文档后，系统的自动化流水线会自动重构 FAISS 索引。
4.  **关系型数据库 (`*.db`)**
    本地 SQLite 用户/会话数据库已被忽略。项目首次启动时，Flask 服务会自动映射 SQLAlchemy 模型，并生成全新的空表结构。

### 3. 配置与启动

请配置好相关的环境变量（如大模型 API Key），然后启动服务：

```bash
python app.py
```
服务默认在 `http://127.0.0.1:5000` 运行。
