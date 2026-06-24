from collections.abc import Callable
from typing import Any


class AiScoringContext:
    """Holds the currently active AI scoring use case and allows runtime model switching.

    build_use_case is called with the new model name each time select_model is invoked.
    configure_sdk is called first to reconfigure the Agents SDK client for the new provider.
    """

    def __init__(
        self,
        initial_model: str,
        initial_use_case: Any,
        build_use_case: Callable[[str], Any],
        configure_sdk: Callable[[str], None],
    ) -> None:
        self._active_model = initial_model
        self._use_case = initial_use_case
        self._build_use_case = build_use_case
        self._configure_sdk = configure_sdk

    @property
    def use_case(self) -> Any:
        return self._use_case

    @property
    def active_model(self) -> str:
        return self._active_model

    def select_model(self, model: str) -> None:
        self._configure_sdk(model)
        self._use_case = self._build_use_case(model)
        self._active_model = model
