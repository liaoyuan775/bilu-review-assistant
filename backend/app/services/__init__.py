"""
业务服务层 — 审查流程编排、规则引擎、文档解析与被害人信息提取。

包含四个核心服务模块：
- analyzer:    本地规则分析引擎（demo 模式下使用）
- parser:      文档格式解析（PDF/DOCX → ParsedDocument）
- qwen:        Qwen 多模态模型调用与结构化结果验证
- review:      审查任务生命周期编排（创建→处理→完成→归档）
- victim_profile:  笔录文本中的被害人基础信息提取
"""
