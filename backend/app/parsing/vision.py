"""
图像转写服务 — 将扫描页或 DOCX 内嵌图片发送给多模态 VLM 转写。

触发场景：
1. DOCX 中正文/页眉/页脚引用的图片，每张调用一次
2. PDF 中某页原生文本 < 20 字时整页渲染为 2x 图片
3. PDF 中某页原生文本 >= 20 字且含嵌入图片时逐图转写

VLM 请求走 OpenAI-compatible /chat/completions 接口，
要求模型返回 {paragraphs: [...], confidence: 0.0} JSON。
"""

import base64
import json
import logging
import re
from time import perf_counter

import httpx

from app.core.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL
from app.core.development_logging import log_event, log_payload
from app.core.errors import AppError


def _parse_response(content: str) -> dict:
    """从 VLM 响应文本中提取段落和置信度 JSON。"""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise AppError("invalid_vision_response", "多模态模型未返回有效 JSON。", 502)
    try:
        payload = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise AppError("invalid_vision_response", "多模态模型返回的 JSON 无法解析。", 502) from exc
    paragraphs = payload.get("paragraphs")
    confidence = payload.get("confidence")
    if not isinstance(paragraphs, list) or not all(isinstance(item, str) for item in paragraphs):
        raise AppError("invalid_vision_response", "多模态模型缺少有效的段落列表。", 502)
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise AppError("invalid_vision_response", "多模态模型缺少有效的识别置信度。", 502)
    return {
        "paragraphs": [" ".join(item.split()) for item in paragraphs if item.strip()],
        "confidence": float(confidence),
    }


async def transcribe_image(image: bytes, media_type: str = "image/png") -> dict:
    """将图片发送给多模态 VLM 并返回转写的段落和置信度。

    Args:
        image: 图片的二进制内容。
        media_type: 图片的 MIME 类型（如 "image/png"）。

    Returns:
        包含 paragraphs（字符串列表）和 confidence（0-1 浮点数）的字典。

    Raises:
        AppError("model_not_configured"): 模型未配置。
        AppError("model_unreachable"): 网络/HTTP 错误。
        AppError("invalid_vision_response"): 响应格式不符合预期。
    """
    if not all([QWEN_BASE_URL, QWEN_API_KEY, QWEN_MODEL]):
        raise AppError("model_not_configured", "多模态模型尚未配置，无法识别扫描页或文档图片。", 503)
    data_url = f"data:{media_type};base64,{base64.b64encode(image).decode('ascii')}"
    prompt = (
        "你是公安机关询问笔录的文档识别助手。请忠实转写图片中的全部可见文字，"
        "保持问答、金额、账号、时间、流水号等原始信息，不补写、不推断。"
        "只返回 JSON：{\"paragraphs\":[\"...\"],\"confidence\":0.0}。"
        "paragraphs 按阅读顺序分段；confidence 为本页整体识别置信度（0 到 1）。"
    )
    started = perf_counter()
    log_event(logging.INFO, "vision.request_started", media_type=media_type, bytes=len(image), model=QWEN_MODEL)
    log_payload("vision.prompt", prompt, media_type=media_type)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0), trust_env=False) as client:
            response = await client.post(
                f"{QWEN_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {QWEN_API_KEY}"},
                json={
                    "model": QWEN_MODEL,
                    "temperature": 0,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }],
                },
            )
    except httpx.HTTPError as exc:
        log_event(logging.WARNING, "vision.request_failed", error_type=type(exc).__name__, duration_ms=round((perf_counter() - started) * 1000))
        raise AppError("model_unreachable", "多模态模型当前不可达，请检查网络或模型配置。", 503) from exc
    if not response.is_success:
        log_event(logging.WARNING, "vision.http_failed", status_code=response.status_code, duration_ms=round((perf_counter() - started) * 1000))
        raise AppError("model_request_failed", f"多模态模型返回 HTTP {response.status_code}。", 502)
    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AppError("invalid_vision_response", "多模态模型未返回有效响应。", 502) from exc
    if not isinstance(content, str):
        raise AppError("invalid_vision_response", "多模态模型未返回文本内容。", 502)
    log_payload("vision.raw_response", content, media_type=media_type)
    parsed = _parse_response(content)
    log_event(logging.INFO, "vision.request_completed", duration_ms=round((perf_counter() - started) * 1000), paragraph_count=len(parsed["paragraphs"]), confidence=parsed["confidence"])
    return parsed
