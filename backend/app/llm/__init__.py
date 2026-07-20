"""
llm 包 — 大语言模型交互层

本包封装与外部大语言模型（当前为 Qwen）的 HTTP 通信。
只提供严格 JSON Schema 请求与能力健康检查，不使用 Tool Calling 或 plain JSON 降级。
依赖 core/ 和 data/ 包。

模块清单：
  qwen.py  OpenAI-compatible HTTP 客户端
"""
