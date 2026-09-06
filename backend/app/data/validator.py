from .repository import StudyCaseRepository


def validate_repository(repository: StudyCaseRepository) -> dict:
    return {"case_count": len(repository.cases), "warnings": list(repository._warnings)}
