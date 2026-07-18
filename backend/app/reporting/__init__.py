"""
reporting 包 — 产物生成与归档层

本包负责审查结果的最终输出：审查报告 PDF/DOCX/JSON 生成、
产物归档门禁检查与哈希验证。是流水线的最后环节。
依赖 core/、parsing/ 和 storage/ 包。

模块清单：
  reports.py       审查报告数据组装和结构化 JSON 生成
  docx_report.py   补问清单 DOCX 生成
  report_labels.py 规则事实路径的中文标签映射
  archive.py       归档门禁检查和艺术哈希验证
  analyzer.py      文档统计分析
"""
