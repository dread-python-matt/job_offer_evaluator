from app.application.ports import AvailableModel, AvailableModelsProvider


class CompositeAvailableModelsProvider(AvailableModelsProvider):
    def __init__(self, providers: list[AvailableModelsProvider]) -> None:
        self._providers = providers

    def list_models(self) -> list[AvailableModel]:
        result: list[AvailableModel] = []
        for provider in self._providers:
            result.extend(provider.list_models())
        return result
