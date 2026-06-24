from collections.abc import Callable
from typing import Any

from app.application.ports import SelectedModelRepository


class AiScoringContext:
    """Resolves the active AI scoring use case from the persisted model selection, so
    every worker agrees on the current model and switches survive restarts.

    The active model is read from `repository` (falling back to `default_model` when
    nothing is selected yet). The built use case is cached per process and rebuilt
    whenever the persisted model changes — so a switch made on one worker is picked up
    by the others on their next request. `configure_sdk` runs before each (re)build.
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
        self._cached_model: str | None = None
        self._use_case: Any = None

    @property
    def active_model(self) -> str:
        return self._repository.get() or self._default_model

    @property
    def use_case(self) -> Any:
        model = self.active_model
        if self._use_case is None or self._cached_model != model:
            self._rebuild(model)
        return self._use_case

    def select_model(self, model: str) -> None:
        self._repository.set(model)
        self._rebuild(model)

    def _rebuild(self, model: str) -> None:
        self._configure_sdk(model)
        self._use_case = self._build_use_case(model)
        self._cached_model = model
