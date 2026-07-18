"""
llm 包 — 大语言模型交互层

本包封装与外部大语言模型（当前为 Qwen）的 HTTP 通信。
提供结构化请求（JSON Schema strict / tool call fallback）和健康检查。
依赖 core/ 和 data/ 包。

模块清单：
  qwen.py  OpenAI-compatible HTTP 客户端
"""
