from backend.app.schemas.migration import MigrationCreate, MigrationRecord
from backend.app.services.persistence_service import persistence_service


class MigrationService:
    def create(self, request: MigrationCreate) -> MigrationRecord:
        return persistence_service.save_migration_request(request)

    def get(self, request_id: str) -> MigrationRecord | None:
        return persistence_service.get_migration_request(request_id)


migration_service = MigrationService()
