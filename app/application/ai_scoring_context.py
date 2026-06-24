from collections.abc import Callable
from typing import Any

from app.application.ports import SelectedModelRepository


class AiScoringContext:
    """Resolves each user's active AI scoring use case from their persisted model
    selection, so every worker agrees on a user's model and switches survive restarts.

    A user's active model is read from `repository` (falling back to `default_model`
    when they haven't selected one). Built use cases are cached **per model** and shared
    across users on the same model; a model is (re)built lazily, with `configure_sdk`
    run once before each build.
    """

    def __init__(
        self,
        repository: SelectedModelRepository,
        build_use_case: Callable[[str], Any],
        configure_sdk: Callable[[str], None],
        default_model: str = "",
    ) -> None:
        self._repository = repository
        self._build_use_case = build_use_case
        self._configure_sdk = configure_sdk
        self._default_model = default_model
        self._use_cases_by_model: dict[str, Any] = {}

    def active_model_for(self, user_id: str) -> str:
        return self._repository.get(user_id) or self._default_model

    def use_case_for(self, user_id: str) -> Any:
        return self._use_case_for_model(self.active_model_for(user_id))

    def select_model(self, user_id: str, model: str) -> None:
        self._repository.set(user_id, model)
        self._use_case_for_model(model)  # warm the cache so the switch is ready to serve

    def _use_case_for_model(self, model: str) -> Any:
        if model not in self._use_cases_by_model:
            self._configure_sdk(model)
            self._use_cases_by_model[model] = self._build_use_case(model)
        return self._use_cases_by_model[model]
