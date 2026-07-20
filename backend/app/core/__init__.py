"""
core 包 — 应用基础层

本包包含整个应用最底层的类型定义和工具，所有其他包都依赖本包。
不依赖应用内任何其他包。

模块清单：
  config.py              环境变量与运行时配置
  errors.py              统一异常层次结构
  models.py              核心 Pydantic 数据模型
  template_models.py     模板审查专用的 Pydantic 模型
  development_logging.py 结构化日志工具
"""
