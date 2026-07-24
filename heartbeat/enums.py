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
class checkResult:
    status: Status
    status_code: int|None
    error: str
    response_time:float|None
    body_size:int|None
    checked_at:datetime