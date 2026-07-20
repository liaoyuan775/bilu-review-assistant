"""
应用级结构化异常 — 统一错误码、HTTP 状态码与重试策略。

设计原则：
- 所有已知业务异常都通过 AppError 显式抛出，避免 API 层产生 500。
- retry_strategy 字段告知调用方模型应如何重试：
  - "schema": 保持 JSON Schema 策略重试（网络抖动 / 临时错误）。
  - None:     不重试（鉴权 / 配置错误）。
- rule_id / field / correction_hint 用于定位并修正模型输出的具体问题。
"""


class AppError(Exception):
    """应用级统一异常 — 所有已知业务错误都使用此类抛出。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        *,
        retry_strategy: str | None = None,
        rule_id: str | None = None,
        field: str | None = None,
        correction_hint: str | None = None,
    ):
        super().__init__(message)
        self.code = code                # 机器可读的错误码（如 "model_unreachable"）
        self.message = message          # 面向用户的错误描述
        self.status_code = status_code  # HTTP 响应状态码
        self.retry_strategy = retry_strategy  # 模型重试策略（schema / tool / None）
        self.rule_id = rule_id          # 出错的规则 ID（模型校验失败时使用）
        self.field = field              # 出错字段名（结构化校验失败时使用）
        self.correction_hint = correction_hint  # 给模型的修正提示，用于下次重试
