import logging
import httpx

logger=logging.getLogger(__name__)


def send_webhook(config:dict,payload:dict)->None:
    url=config.get("url")
    if not url:
        return
    try:
        resp=httpx.post(url,json=payload,timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.error("Webhook to %s failed %s" ,url,e)


def send_telegram(config:dict,payload:dict)->None:
    from django.conf import settings
    token=settings.TELEGRAM_BOT_TOKEN
    chat_id=config.get("chat_id")
    if not token or not chat_id:
        return

    m= payload["monitor"]

    if payload["event"]=="down":
        text=(
            f"\U0001f6a8 <b>DOWN:</b> {m['name']}\n"
            f"URL: {m['url']}\n"
            f"Status: {payload['result']['status_code']}\n"
            f"Time: {payload['result']['checked_at']}"
        )
    else:
        text = (
            f"\u2705 <b>UP:</b> {m['name']}\n"
            f"URL: {m['url']}\n"
            f"Recovered: {payload['recovered_at']}"
        )

    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        ).raise_for_status()
    except Exception as e:
        logger.error("Telegram failed: %s", e)


def send_discord(config: dict, payload: dict) -> None:
    url = config.get("webhook_url")
    if not url:
        return
    is_down = payload["event"] == "down"
    embed = {
        "embeds": [{
            "title": f"{'\U0001f6a8 DOWN' if is_down else '\u2705 UP'}: {payload['monitor']['name']}",
            "color": 0xFF4444 if is_down else 0x44FF44,
            "fields": [{"name": "URL", "value": payload["monitor"]["url"]}],
        }]
    }
    try:
        httpx.post(url, json=embed, timeout=15).raise_for_status()
    except Exception as e:
        logger.error("Discord failed: %s", e)


DISPATCHERS = {
    "webhook": send_webhook,
    "telegram": send_telegram,
    "discord": send_discord,
}


def dispatch(provider: str, config: dict, payload: dict) -> None:
    fn = DISPATCHERS.get(provider)
    if fn:
        fn(config, payload)