from django.db import models
from dataclasses import dataclass
from datetime import datetime

class HttpMethod(models.TextChoices):
    GET='GET'
    HEAD='HEAD'


class Status(models.TextChoices):
    UP='UP'
    DOWN='DOWN'
    DEGRADED='DEGRADED'


@dataclass
class CheckResult:
    status: Status
    status_code: int|None
    error: str
    response_time_ms:float|None
    body_size:int|None
    checked_at:datetime

    def to_dict(self)->dict:
        return {
            "status":self.status,
            "status_code":self.status_code,
            "error":self.error,
            "response_time_ms":self.response_time_ms,
            "body_size":self.body_size,
            "checked_at":self.checked_at.isoformat(),

        }