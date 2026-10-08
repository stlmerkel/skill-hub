from dataclasses import dataclass

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    level: str
    check_id: str
    path: str
    message: str
    line: int | None = None
