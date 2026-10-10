from __future__ import annotations


class LLMFailure(Exception):
    """The model did not produce a usable line. The world must stay unchanged."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


USER_MESSAGES = {
    "timeout": "Ответ не успел собраться. Можно повторить или взять заготовку.",
    "invalid_json": "Ответ модели не разобрать. Можно повторить или взять заготовку.",
    "empty_reply": "Модель прислала пустой ответ. Можно повторить или взять заготовку.",
    "server_down": "Языковая модель недоступна. Можно повторить или взять заготовку.",
    "unknown_model": "Такая модель на сервере не найдена. Проверьте имя модели или возьмите заготовку.",
    "context_too_large": "Память разговора не помещается в окно модели. Можно взять заготовку.",
}
