class AppError(Exception):
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
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_strategy = retry_strategy
        self.rule_id = rule_id
        self.field = field
        self.correction_hint = correction_hint
