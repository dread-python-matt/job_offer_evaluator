from app.application.ports import ExternalUsageProvider, ModelUsageSummary


class NoExternalUsageProvider(ExternalUsageProvider):
    def get_today_usage(self) -> list[ModelUsageSummary]:
        return []
