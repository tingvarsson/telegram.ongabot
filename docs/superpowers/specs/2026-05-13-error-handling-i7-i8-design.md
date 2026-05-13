# Error Handling: I7 & I8

**Date:** 2026-05-13

## Overview

Two targeted hardening improvements:

- **I7** — Wrap Telegram API calls in job callbacks and multi-step event creation so failures are logged and non-fatal.
- **I8** — Wrap `schedule_all_event_jobs` in `post_init` so a corrupt pickle doesn't crash startup.

## Scope

**In scope:**
- Job callbacks: `create_event_callback`, `complete_past_events_callback`
- Multi-step create flow: `eventcreator.py:create_event`
- Startup scheduling: `ongabot.py:post_init`

**Out of scope:**
- Command handler `reply_text`/`send_message` calls — the global error handler already logs these.
- Rollback/cleanup of partial state (e.g. deleting a poll that was sent when the subsequent pin fails).

## I7 — Surgical TelegramError Handling

### `eventcreator.py:create_event`

Three sequential API calls; only `send_poll` is fatal. Status-message and pin failures are non-fatal — the event is still tracked.

```
send_poll       → fatal: log error and return (no event object to register)
send_status_message → non-fatal: log error, continue (event has no status message)
pin             → non-fatal: log error, continue (event is registered, just unpinned)
```

Each step wrapped individually with `except TelegramError`.

### `ongabot.py:complete_past_events_callback`

Per-event try/except around `update_status_message` so one chat's API failure doesn't abort processing for all other chats. `remove_pinned_poll` already has its own try/except in `chat.py`.

### Import

`from telegram.error import TelegramError` added to `eventcreator.py` and `ongabot.py`.

## I8 — Startup Bot Data Validation

### `ongabot.py:post_init`

Wrap `bot_data.schedule_all_event_jobs(...)` in `try/except Exception`. On failure:
- Log a clear `ERROR` message indicating recurring polls will not fire.
- Continue — bot starts normally, operator is alerted via logs.

No data is discarded. The `BotData.__setstate__`, `Chat.__setstate__`, and `Event.__setstate__` methods already defend against missing attributes from older pickles. This guard covers the residual case where deserialization succeeds but scheduling itself raises.

## Files Changed

| File | Change |
|------|--------|
| `ongabot/eventcreator.py` | Add `TelegramError` import; wrap `send_poll`, `send_status_message`, `pin` individually |
| `ongabot/ongabot.py` | Add `TelegramError` import; per-event wrap in `complete_past_events_callback`; try/except around `schedule_all_event_jobs` in `post_init` |

## Testing

- Unit test: `create_event` where `send_poll` raises `TelegramError` → function returns early, no event added to chat.
- Unit test: `create_event` where `send_status_message` raises → event still added to chat.
- Unit test: `create_event` where `pin` raises → event still added and pinned-poll not registered.
- Unit test: `complete_past_events_callback` where `update_status_message` raises for one event → other events still processed.
- Unit test: `post_init` where `schedule_all_event_jobs` raises → no exception propagates, error is logged.
