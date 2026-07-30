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


def send_slack(config: dict, payload: dict) -> None:
    url = config.get("webhook_url")
    if not url:
        return
    is_down = payload["event"] == "down"
    m = payload["monitor"]
    text = (
        f"{'\U0001f6a8' if is_down else '\u2705'} *{'DOWN' if is_down else 'UP'}: {m['name']}*\n"
        f"URL: {m['url']}\n"
        f"{'Status: ' + str(payload['result']['status_code']) + '\nTime: ' + payload['result']['checked_at'] if is_down else 'Recovered: ' + payload['recovered_at']}"
    )
    try:
        httpx.post(url, json={"text": text}, timeout=15).raise_for_status()
    except Exception as e:
        logger.error("Slack failed: %s", e)


def send_pushover(config: dict, payload: dict) -> None:
    from django.conf import settings
    token = settings.PUSHOVER_APP_TOKEN
    user_key = config.get("user_key")
    if not token or not user_key:
        return
    is_down = payload["event"] == "down"
    m = payload["monitor"]
    title = f"{'\U0001f6a8 DOWN' if is_down else '\u2705 UP'}: {m['name']}"
    message = (
        f"{m['url']}\n"
        f"{'Status: ' + str(payload['result']['status_code']) + '\nTime: ' + payload['result']['checked_at'] if is_down else 'Recovered: ' + payload['recovered_at']}"
    )
    try:
        httpx.post(
            "https://api.pushover.net/1/messages.json",
            data={"token": token, "user": user_key, "title": title, "message": message},
            timeout=15,
        ).raise_for_status()
    except Exception as e:
        logger.error("Pushover failed: %s", e)


def send_teams(config: dict, payload: dict) -> None:
    url = config.get("webhook_url")
    if not url:
        return
    is_down = payload["event"] == "down"
    m = payload["monitor"]
    title = f"{'\U0001f6a8' if is_down else '\u2705'} {'DOWN' if is_down else 'UP'}: {m['name']}"
    text = (
        f"{m['url']}\n"
        f"{'Status: ' + str(payload['result']['status_code']) if is_down else 'Recovered: ' + payload['recovered_at']}"
    )
    card = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title,
        "title": title,
        "text": text,
        "themeColor": "FF4444" if is_down else "44FF44",
    }
    try:
        httpx.post(url, json=card, timeout=15).raise_for_status()
    except Exception as e:
        logger.error("Teams failed: %s", e)


def send_googlechat(config: dict, payload: dict) -> None:
    url = config.get("webhook_url")
    if not url:
        return
    is_down = payload["event"] == "down"
    m = payload["monitor"]
    text = (
        f"{'\U0001f6a8' if is_down else '\u2705'} {'DOWN' if is_down else 'UP'}: {m['name']}\n"
        f"URL: {m['url']}\n"
        f"{'Status: ' + str(payload['result']['status_code']) if is_down else 'Recovered: ' + payload['recovered_at']}"
    )
    try:
        httpx.post(url, json={"text": text}, timeout=15).raise_for_status()
    except Exception as e:
        logger.error("Google Chat failed: %s", e)


def send_mattermost(config: dict, payload: dict) -> None:
    url = config.get("webhook_url")
    if not url:
        return
    is_down = payload["event"] == "down"
    m = payload["monitor"]
    text = (
        f"{'\U0001f6a8' if is_down else '\u2705'} **{'DOWN' if is_down else 'UP'}: {m['name']}**\n"
        f"URL: {m['url']}\n"
        f"{'Status: ' + str(payload['result']['status_code']) if is_down else 'Recovered: ' + payload['recovered_at']}"
    )
    try:
        httpx.post(url, json={"text": text}, timeout=15).raise_for_status()
    except Exception as e:
        logger.error("Mattermost failed: %s", e)


def send_zulip(config: dict, payload: dict) -> None:
    url = config.get("webhook_url")
    if not url:
        return
    is_down = payload["event"] == "down"
    m = payload["monitor"]
    content = (
        f"**{'DOWN' if is_down else 'UP'}**: {m['name']}\n"
        f"URL: {m['url']}\n"
        f"{'Status: ' + str(payload['result']['status_code']) if is_down else 'Recovered: ' + payload['recovered_at']}"
    )
    try:
        httpx.post(url, json={"topic": "PingPilot", "content": content}, timeout=15).raise_for_status()
    except Exception as e:
        logger.error("Zulip failed: %s", e)


def send_pagerduty(config: dict, payload: dict) -> None:
    routing_key = config.get("routing_key")
    if not routing_key:
        return
    is_down = payload["event"] == "down"
    m = payload["monitor"]
    body = {
        "routing_key": routing_key,
        "event_action": "trigger" if is_down else "resolve",
        "payload": {
            "summary": f"{'DOWN' if is_down else 'UP'}: {m['name']}",
            "severity": "critical" if is_down else "info",
            "source": m["url"],
            "custom_details": {"status_code": payload.get("result", {}).get("status_code")} if is_down else {},
        },
    }
    try:
        httpx.post(
            "https://events.pagerduty.com/v2/enqueue",
            json=body,
            timeout=15,
        ).raise_for_status()
    except Exception as e:
        logger.error("PagerDuty failed: %s", e)


def _send_webhook_post(url: str, payload: dict, provider_name: str) -> None:
    is_down = payload["event"] == "down"
    m = payload["monitor"]
    text = (
        f"{'\U0001f6a8' if is_down else '\u2705'} {'DOWN' if is_down else 'UP'}: {m['name']}\n"
        f"URL: {m['url']}\n"
        f"{'Status: ' + str(payload['result']['status_code']) if is_down else 'Recovered: ' + payload['recovered_at']}"
    )
    try:
        httpx.post(url, json={"text": text}, timeout=15).raise_for_status()
    except Exception as e:
        logger.error("%s failed: %s", provider_name, e)


def send_ntfy(config: dict, payload: dict) -> None:
    _send_webhook_post(config.get("webhook_url", ""), payload, "ntfy")


def send_gotify(config: dict, payload: dict) -> None:
    _send_webhook_post(config.get("webhook_url", ""), payload, "Gotify")


def send_rocketchat(config: dict, payload: dict) -> None:
    _send_webhook_post(config.get("webhook_url", ""), payload, "Rocket.Chat")


def send_zapier(config: dict, payload: dict) -> None:
    _send_webhook_post(config.get("webhook_url", ""), payload, "Zapier")


def send_make(config: dict, payload: dict) -> None:
    _send_webhook_post(config.get("webhook_url", ""), payload, "Make")


def send_n8n(config: dict, payload: dict) -> None:
    _send_webhook_post(config.get("webhook_url", ""), payload, "n8n")


def send_ifttt(config: dict, payload: dict) -> None:
    _send_webhook_post(config.get("webhook_url", ""), payload, "IFTTT")


def send_chime(config: dict, payload: dict) -> None:
    url = config.get("webhook_url")
    if not url:
        return
    is_down = payload["event"] == "down"
    m = payload["monitor"]
    content = (
        f"{'\U0001f6a8' if is_down else '\u2705'} {'DOWN' if is_down else 'UP'}: {m['name']}\n"
        f"URL: {m['url']}\n"
        f"{'Status: ' + str(payload['result']['status_code']) if is_down else 'Recovered: ' + payload['recovered_at']}"
    )
    try:
        httpx.post(url, json={"Content": content}, timeout=15).raise_for_status()
    except Exception as e:
        logger.error("Amazon Chime failed: %s", e)


def send_opsgenie(config: dict, payload: dict) -> None:
    api_key = config.get("api_key")
    if not api_key:
        return
    is_down = payload["event"] == "down"
    m = payload["monitor"]
    body = {
        "message": f"{'DOWN' if is_down else 'UP'}: {m['name']}",
        "alias": f"pingpilot-{m['id']}",
        "details": {
            "url": m["url"],
            "status_code": str(payload.get("result", {}).get("status_code", "")) if is_down else "",
            "monitor_id": str(m["id"]),
        },
        "priority": "P1" if is_down else "P5",
    }
    try:
        httpx.post(
            "https://api.opsgenie.com/v2/alerts",
            json=body,
            headers={"Authorization": f"GenieKey {api_key}"},
            timeout=15,
        ).raise_for_status()
    except Exception as e:
        logger.error("Opsgenie failed: %s", e)


def send_splunk(config: dict, payload: dict) -> None:
    routing_key = config.get("routing_key")
    if not routing_key:
        return
    is_down = payload["event"] == "down"
    m = payload["monitor"]
    body = {
        "message_type": "CRITICAL" if is_down else "RECOVERY",
        "entity_id": f"pingpilot-{m['id']}",
        "state_message": (
            f"{'DOWN' if is_down else 'UP'}: {m['name']}\n"
            f"URL: {m['url']}\n"
            f"{'Status: ' + str(payload['result']['status_code']) if is_down else 'Recovered: ' + payload['recovered_at']}"
        ),
        "entity_display_name": m["name"],
        "monitoring_tool": "PingPilot",
    }
    try:
        httpx.post(
            f"https://api.victorops.com/api-public/v1/alert/{routing_key}",
            json=body,
            timeout=15,
        ).raise_for_status()
    except Exception as e:
        logger.error("Splunk On-Call failed: %s", e)


def send_matrix(config: dict, payload: dict) -> None:
    _send_webhook_post(config.get("webhook_url", ""), payload, "Matrix")


def send_signl4(config: dict, payload: dict) -> None:
    _send_webhook_post(config.get("webhook_url", ""), payload, "SIGNL4")


def send_xmatters(config: dict, payload: dict) -> None:
    _send_webhook_post(config.get("webhook_url", ""), payload, "xMatters")


DISPATCHERS = {
    "webhook": send_webhook,
    "telegram": send_telegram,
    "discord": send_discord,
    "slack": send_slack,
    "teams": send_teams,
    "pushover": send_pushover,
    "googlechat": send_googlechat,
    "mattermost": send_mattermost,
    "zulip": send_zulip,
    "pagerduty": send_pagerduty,
    "ntfy": send_ntfy,
    "gotify": send_gotify,
    "rocketchat": send_rocketchat,
    "zapier": send_zapier,
    "make": send_make,
    "n8n": send_n8n,
    "ifttt": send_ifttt,
    "chime": send_chime,
    "matrix": send_matrix,
    "signl4": send_signl4,
    "xmatters": send_xmatters,
    "opsgenie": send_opsgenie,
    "splunk": send_splunk,
}


def dispatch(provider: str, config: dict, payload: dict) -> None:
    fn = DISPATCHERS.get(provider)
    if fn:
        fn(config, payload)