import asyncio
import logging
import time

import httpx
from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand

from heartbeat.alerts import evaluate_and_alert
from heartbeat.checker import check_monitor
from heartbeat.incidents import open_or_close_incident
from heartbeat.scheduler import get_due_monitors, next_sleep
from heartbeat.services import save_result

logger = logging.getLogger(__name__)


async def ttfb_hook(response):
    response.extensions["ttfb_time"] = time.perf_counter()


class Command(BaseCommand):
    help = "Run the heartbeat monitoring worker"

    def handle(self, *args, **options):
        logger.info("Worker started")
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            logger.info("Worker shutting down")

    async def _run(self):
        get_due = sync_to_async(get_due_monitors)
        sleep_dur = sync_to_async(next_sleep)
        semaphore = asyncio.Semaphore(100)
        async with httpx.AsyncClient(timeout=10, event_hooks={"response": [ttfb_hook]}) as client:
            while True:
                monitors = await get_due()
                logger.info("Checking %d monitors...", len(monitors))

                async def process(monitor):
                    async with semaphore:
                        result = await check_monitor(monitor, client)
                        await sync_to_async(save_result)(monitor, result)
                        await sync_to_async(evaluate_and_alert)(monitor, result)
                        await sync_to_async(open_or_close_incident)(monitor, result)
                        logger.info(
                            "monitor=%s status=%s latency=%.0fms error=%s",
                            monitor.name, result.status,
                            result.response_time_ms or 0, result.error,
                        )

                if monitors:
                    await asyncio.gather(*[process(m) for m in monitors])

                seconds = await sleep_dur(monitors)
                await asyncio.sleep(seconds)