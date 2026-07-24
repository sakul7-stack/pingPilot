import asyncio
from datetime import datetime

import httpx
from .enums import checkResult,Status
from models import Monitor

TRANSIENT_ERRORS={"TIMEOUT","CONNECTION_RESET","HTTP_502","HTTP_503","HTTP_504"}