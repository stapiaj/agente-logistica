"""Human alerts through a Telegram bot (phase 3b).

Telegram's Bot API is HTTP too: POST https://api.telegram.org/bot<TOKEN>/<method>
with a JSON body. Same pattern as Resend (httpx, no SDK).

Three details that matter:
- Plain text, no Markdown: with parse_mode, a stray "_" or "*" written by
  the model makes Telegram REJECT the message. An alert must never be lost
  because of an asterisk.
- 4096 characters per message: longer alerts (with an email draft) are
  split at line breaks into numbered parts "(1/2)", "(2/2)". Cutting would
  lose part of the draft the human needs.
- The token travels INSIDE the URL, so error messages never show the URL
  and any copy of the token is replaced by <TOKEN> (no secrets in logs).

No automatic retries here, like email: any failure raises TelegramError,
the agent loop turns it into "technical" and the guardrail takes over.
"""

import sys

import httpx

from app.config import load_telegram_config

API_URL = "https://api.telegram.org/bot{token}/{method}"
MAX_LENGTH = 4096  # Telegram's limit per message
PART_HEADER = "({index}/{total})\n"
TIMEOUT_SECONDS = 10


class TelegramError(Exception):
    """The alert could not be delivered (or we can't be sure it was)."""


def split_message(text: str, limit: int = MAX_LENGTH) -> list[str]:
    """Split a long text into numbered parts of at most `limit` characters.

    Cuts at the last line break that fits (a hard cut only if a single line
    is longer than a whole message). Short texts go as they are.
    """
    if len(text) <= limit:
        return [text]
    room = limit - len(PART_HEADER.format(index=99, total=99))  # space for "(i/n)"
    chunks = []
    remaining = text
    while len(remaining) > room:
        cut = remaining.rfind("\n", 0, room)
        if cut <= 0:
            cut = room
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    chunks.append(remaining)
    total = len(chunks)
    return [PART_HEADER.format(index=i, total=total) + chunk for i, chunk in enumerate(chunks, 1)]


def redact(text: str, token: str) -> str:
    """Hide the bot token in any text that could end up on screen or in a log."""
    return text.replace(token, "<TOKEN>") if token else text


def raise_for_error(response: httpx.Response, token: str) -> None:
    """Turn a Telegram error answer into a readable TelegramError (token hidden)."""
    code = response.status_code
    if code < 400:
        return
    if code == 401:
        hint = "wrong TELEGRAM_BOT_TOKEN"
    elif code == 400:
        hint = "bad request, usually a wrong TELEGRAM_CHAT_ID (chat not found)"
    elif code == 403:
        hint = "the bot can't write to this chat (send it a message first, or it was blocked)"
    elif code == 429:
        hint = "too many messages, Telegram rate limit"
    elif code >= 500:
        hint = "Telegram is failing on its side"
    else:
        hint = "unexpected answer from Telegram"
    raise TelegramError(redact(f"Telegram HTTP {code}: {hint}. Response: {response.text[:300]}", token))


def _call(token: str, method: str, payload: dict | None = None) -> dict:
    """One call to the Bot API. Raises TelegramError, never shows the URL."""
    url = API_URL.format(token=token, method=method)
    try:
        response = httpx.post(url, json=payload or {}, timeout=TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        # "from None": the original exception could carry the URL (and the token).
        raise TelegramError("Telegram did not answer in time "
                            "(the alert may or may not have arrived)") from None
    except httpx.HTTPError as error:
        raise TelegramError(redact(f"could not reach Telegram: {type(error).__name__}: {error}",
                                   token)) from None
    raise_for_error(response, token)
    return response.json()


def send_message(text: str) -> int:
    """Send an alert to the configured chat. Returns how many messages it took."""
    token, chat_id = load_telegram_config()
    parts = split_message(text)
    for part in parts:  # in order; if one fails, the error says it
        _call(token, "sendMessage", {"chat_id": chat_id, "text": part})
    return len(parts)


def find_chat_ids() -> list[tuple[str, str]]:
    """Chats that wrote to the bot recently: (chat_id, name). Setup helper."""
    token, _ = load_telegram_config(need_chat_id=False)
    updates = _call(token, "getUpdates").get("result", [])
    chats = {}
    for update in updates:
        chat = (update.get("message") or {}).get("chat")
        if chat:
            name = chat.get("first_name") or chat.get("title") or chat.get("username") or "?"
            chats[str(chat["id"])] = name
    return list(chats.items())


if __name__ == "__main__":
    # Setup:  python -m app.integrations.telegram --find-chat-id
    # Test:   python -m app.integrations.telegram
    if "--find-chat-id" in sys.argv:
        found = find_chat_ids()
        if not found:
            print("No messages found: open your bot in Telegram, send it 'hola' and try again.")
        for chat_id, name in found:
            print(f"TELEGRAM_CHAT_ID={chat_id}   ({name})")
    else:
        count = send_message("[TEST] Agente Logistica: test alert from Python.")
        print(f"Sent ({count} message(s)).")
