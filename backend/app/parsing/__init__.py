"""
parsing 包 — 文档解析层

本包负责将上传的 DOCX/PDF 文件解析为统一的 ParsedDocument 结构。
包含格式识别、安全展开、OCR/图像转写、问答重建等功能。
依赖 core/ 和 data/ 包。

模块清单：
  parser.py           解析入口，按文件扩展名分派到 DOCX/PDF 分支
  openxml.py          DOCX 的 ZIP 安全展开与 OpenXML 部件读取
  question_answer.py  对解析后的段落执行问答对重建
  vision.py           将 DOCX/PDF 中的图片发送给 VLM 转写为文字
"""
