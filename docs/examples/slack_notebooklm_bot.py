"""Slack → Claude → NotebookLM Bot

Listens for @mentions in Slack channels and runs each question through the
Claude ↔ NotebookLM pipeline (claude_notebooklm_bridge.py), then replies
in-thread with a formatted draft answer.

Notebook selection is managed per-channel via slash commands:
    /notebooklm list            – list available notebooks
    /notebooklm use <name>      – set notebook for this channel
    /notebooklm status          – show current channel's notebook
    /notebooklm clear           – remove channel configuration

Prerequisites:
    pip install "notebooklm-py[claude,slack]"
    notebooklm login            # authenticate with Google

Slack App setup (api.slack.com/apps):
    1. Enable Socket Mode; generate an App-level token with connections:write
    2. Bot Token OAuth Scopes: app_mentions:read, channels:history, chat:write, commands
    3. Subscribe to bot events: app_mention
    4. Create slash command /notebooklm (no Request URL needed with Socket Mode)

Environment variables:
    SLACK_BOT_TOKEN     xoxb-...  (required)
    SLACK_APP_TOKEN     xapp-...  (required)
    ANTHROPIC_API_KEY   sk-ant-...  (required)
    NOTEBOOKLM_NOTEBOOK_ID        (optional fallback when channel has no config)
    NOTEBOOKLM_HOME               (optional, overrides ~/.notebooklm)

Usage:
    python docs/examples/slack_notebooklm_bot.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from notebooklm import NotebookLMClient
from notebooklm.exceptions import (
    AuthError,
    NetworkError,
    NotebookLMError,
    RateLimitError,
    RPCTimeoutError,
)
from notebooklm.paths import get_home_dir
from notebooklm.types import Notebook

# Import the bridge from the sibling example file
sys.path.insert(0, str(Path(__file__).parent))
from claude_notebooklm_bridge import BridgeResult, ClaudeNotebookBridge

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration data types
# ---------------------------------------------------------------------------


@dataclass
class ChannelConfig:
    """Per-channel notebook selection."""

    notebook_id: str
    notebook_title: str
    configured_by: str = ""  # Slack user ID
    configured_at: str = ""  # ISO-8601 timestamp

    def to_dict(self) -> dict:
        return {
            "notebook_id": self.notebook_id,
            "notebook_title": self.notebook_title,
            "configured_by": self.configured_by,
            "configured_at": self.configured_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ChannelConfig:
        return cls(
            notebook_id=data["notebook_id"],
            notebook_title=data.get("notebook_title", ""),
            configured_by=data.get("configured_by", ""),
            configured_at=data.get("configured_at", ""),
        )


class SlackConfig:
    """Loads and saves per-channel notebook config to slack_config.json.

    Uses atomic writes (write to .tmp → os.replace) to prevent corruption.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._channels: dict[str, ChannelConfig] = {}

    def load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._channels = {
                ch_id: ChannelConfig.from_dict(cfg)
                for ch_id, cfg in data.get("channels", {}).items()
            }
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning("Failed to load slack config from %s: %s", self._path, e)

    def save(self) -> None:
        data = {"channels": {ch: cfg.to_dict() for ch, cfg in self._channels.items()}}
        tmp = self._path.with_suffix(".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError as e:
            logger.error("Failed to save slack config: %s", e)

    def get_channel(self, channel_id: str) -> ChannelConfig | None:
        return self._channels.get(channel_id)

    def set_channel(
        self,
        channel_id: str,
        notebook_id: str,
        notebook_title: str,
        *,
        configured_by: str = "",
    ) -> None:
        self._channels[channel_id] = ChannelConfig(
            notebook_id=notebook_id,
            notebook_title=notebook_title,
            configured_by=configured_by,
            configured_at=datetime.now(timezone.utc).isoformat(),
        )
        self.save()

    def remove_channel(self, channel_id: str) -> None:
        self._channels.pop(channel_id, None)
        self.save()


# ---------------------------------------------------------------------------
# Notebook list cache
# ---------------------------------------------------------------------------


class NotebookCache:
    """Short-lived in-memory cache for the notebook list (5-minute TTL)."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._notebooks: list[Notebook] | None = None
        self._expires_at: float = 0.0
        self._ttl = ttl_seconds

    def get(self) -> list[Notebook] | None:
        if self._notebooks is not None and time.monotonic() < self._expires_at:
            return self._notebooks
        return None

    def set(self, notebooks: list[Notebook]) -> None:
        self._notebooks = notebooks
        self._expires_at = time.monotonic() + self._ttl

    def invalidate(self) -> None:
        self._notebooks = None
        self._expires_at = 0.0


# ---------------------------------------------------------------------------
# Block Kit builders
# ---------------------------------------------------------------------------

_SLACK_BLOCK_TEXT_LIMIT = 3000


def build_answer_blocks(result: BridgeResult, notebook_title: str) -> list[dict]:
    """Build Slack blocks for a successful bridge result."""
    answer = result.formatted_answer
    if len(answer) > _SLACK_BLOCK_TEXT_LIMIT:
        answer = answer[: _SLACK_BLOCK_TEXT_LIMIT - 40] + "\n\n_…[truncated — answer too long]_"

    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": answer}},
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"_Notebook: *{notebook_title}*"
                        f" · Refined query: {result.refined_question[:120]}{'…' if len(result.refined_question) > 120 else ''}_"
                    ),
                }
            ],
        },
    ]

    if result.references:
        ref_lines = []
        for ref in result.references[:5]:
            num = f"[{ref['citation_number']}] " if ref.get("citation_number") else "• "
            snippet = (ref.get("cited_text") or "")[:80]
            if snippet:
                ref_lines.append(f"{num}_{snippet}…_")
        if ref_lines:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*Sources cited:*\n" + "\n".join(ref_lines)},
                }
            )

    return blocks


def build_error_blocks(error_msg: str, recoverable: bool = False) -> list[dict]:
    """Build Slack blocks for an error state."""
    icon = ":warning:" if recoverable else ":x:"
    text = f"{icon} {error_msg}"
    if recoverable:
        text += "\n_Run `notebooklm login` and restart the bot._"
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]


def build_notebook_list_blocks(notebooks: list[Notebook], current_nb_id: str | None) -> list[dict]:
    """Build Slack blocks listing all notebooks."""
    if not notebooks:
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":open_file_folder: No notebooks found in your account.\nCreate one at notebooklm.google.com.",
                },
            }
        ]

    lines = []
    for nb in notebooks:
        marker = " ✓" if nb.id == current_nb_id else ""
        lines.append(f"• *{nb.title}*{marker}  `{nb.id[:8]}…` ({nb.sources_count} sources)")

    text = "*Available notebooks:*\n" + "\n".join(lines)
    text += "\n\nUse `/notebooklm use <name>` to configure this channel."
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]


def build_thinking_blocks() -> list[dict]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":hourglass_flowing_sand: 思考中… 查詢 NotebookLM 中",
            },
        }
    ]


def build_help_blocks() -> list[dict]:
    help_text = (
        "*NotebookLM Bot — 說明*\n\n"
        "*@提及* — 向 Bot 提問（Bot 會使用此頻道設定的筆記本作答）\n\n"
        "*Slash Commands:*\n"
        "• `/notebooklm list` — 列出所有可用筆記本\n"
        "• `/notebooklm use <名稱>` — 設定此頻道使用的筆記本\n"
        "• `/notebooklm status` — 查看此頻道目前設定的筆記本\n"
        "• `/notebooklm clear` — 清除此頻道的筆記本設定\n"
        "• `/notebooklm help` — 顯示此說明"
    )
    return [{"type": "section", "text": {"type": "mrkdwn", "text": help_text}}]


# ---------------------------------------------------------------------------
# Main bot class
# ---------------------------------------------------------------------------


class SlackNotebookBot:
    """Slack bot that routes @mentions through ClaudeNotebookBridge."""

    def __init__(self, config: SlackConfig, cache: NotebookCache) -> None:
        self._config = config
        self._cache = cache
        self._app = AsyncApp(token=os.environ["SLACK_BOT_TOKEN"])
        self._handler = AsyncSocketModeHandler(self._app, os.environ["SLACK_APP_TOKEN"])
        self._tasks: set[asyncio.Task] = set()
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self._app.event("app_mention")
        async def on_mention(body: dict, client) -> None:
            await self._handle_mention(body, client)

        @self._app.command("/notebooklm")
        async def on_slash(ack, body: dict, client) -> None:
            await self._handle_slash_command(ack, body, client)

    async def start(self) -> None:
        """Start the bot; handle SIGTERM/SIGINT for graceful shutdown."""
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)

        logger.info("Starting Slack NotebookLM bot (Socket Mode)…")
        handler_task = asyncio.create_task(self._handler.start_async())

        await stop.wait()
        logger.info("Shutdown signal received, waiting for %d task(s)…", len(self._tasks))

        if self._tasks:
            await asyncio.wait(self._tasks, timeout=30)

        handler_task.cancel()
        try:
            await handler_task
        except asyncio.CancelledError:
            pass
        logger.info("Bot stopped.")

    def _create_task(self, coro) -> asyncio.Task:
        """Create a tracked background task; remove it from the set when done."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _handle_mention(self, body: dict, client) -> None:
        event = body.get("event", {})

        # Skip bot messages to prevent loops
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return

        raw_text: str = event.get("text", "")
        # Strip the @mention prefix (<@BOTID>)
        question = re.sub(r"<@[A-Z0-9]+>", "", raw_text).strip()
        if not question:
            return

        channel_id: str = event["channel"]
        thread_ts: str = event.get("thread_ts") or event["ts"]

        # Post a placeholder so the user sees immediate feedback
        resp = await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            blocks=build_thinking_blocks(),
            text="思考中…",
        )
        thinking_ts: str = resp["ts"]

        self._create_task(self._ask_bridge(channel_id, question, thread_ts, thinking_ts, client))

    async def _handle_slash_command(self, ack, body: dict, client) -> None:
        await ack()  # Must respond within 3 seconds
        self._create_task(self._process_slash(body, client))

    # ------------------------------------------------------------------
    # Slash command logic (runs as a background task)
    # ------------------------------------------------------------------

    async def _process_slash(self, body: dict, client) -> None:
        channel_id: str = body["channel_id"]
        user_id: str = body.get("user_id", "")
        raw_text: str = (body.get("text") or "").strip()

        parts = raw_text.split(maxsplit=1)
        subcommand = parts[0].lower() if parts else "help"
        arg = parts[1] if len(parts) > 1 else ""

        if subcommand in ("", "help"):
            await client.chat_postMessage(
                channel=channel_id,
                blocks=build_help_blocks(),
                text="NotebookLM Bot 說明",
            )

        elif subcommand == "list":
            try:
                notebooks = await self._list_notebooks()
                current = self._config.get_channel(channel_id)
                current_id = (
                    current.notebook_id if current else os.environ.get("NOTEBOOKLM_NOTEBOOK_ID")
                )
                await client.chat_postMessage(
                    channel=channel_id,
                    blocks=build_notebook_list_blocks(notebooks, current_id),
                    text="可用筆記本列表",
                )
            except NotebookLMError as e:
                await client.chat_postMessage(
                    channel=channel_id,
                    blocks=build_error_blocks(
                        f"無法取得筆記本清單：{e}", recoverable=isinstance(e, AuthError)
                    ),
                    text="錯誤",
                )

        elif subcommand == "use":
            if not arg:
                await client.chat_postMessage(
                    channel=channel_id,
                    text=":x: 請提供筆記本名稱，例如：`/notebooklm use My Research`",
                )
                return
            try:
                nb = await self._resolve_notebook_by_name(arg)
                if nb is None:
                    notebooks = await self._list_notebooks()
                    await client.chat_postMessage(
                        channel=channel_id,
                        blocks=[
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f":x: 找不到筆記本 `{arg}`。請從以下清單選擇：",
                                },
                            },
                            *build_notebook_list_blocks(notebooks, None),
                        ],
                        text=f"找不到筆記本：{arg}",
                    )
                    return
                self._config.set_channel(
                    channel_id,
                    nb.id,
                    nb.title,
                    configured_by=user_id,
                )
                await client.chat_postMessage(
                    channel=channel_id,
                    text=f":white_check_mark: 此頻道已設定使用筆記本 *{nb.title}*（{nb.sources_count} 個來源）。",
                )
            except NotebookLMError as e:
                await client.chat_postMessage(
                    channel=channel_id,
                    blocks=build_error_blocks(str(e), recoverable=isinstance(e, AuthError)),
                    text="錯誤",
                )

        elif subcommand == "status":
            cfg = self._config.get_channel(channel_id)
            fallback_id = os.environ.get("NOTEBOOKLM_NOTEBOOK_ID")
            if cfg:
                text = f":notebook: 此頻道使用筆記本 *{cfg.notebook_title}*（`{cfg.notebook_id[:8]}…`）"
                if cfg.configured_by:
                    text += f"\n由 <@{cfg.configured_by}> 設定於 {cfg.configured_at[:10]}"
            elif fallback_id:
                text = f":notebook: 使用環境變數預設筆記本 `{fallback_id[:8]}…`（頻道未個別設定）"
            else:
                text = ":grey_question: 此頻道尚未設定筆記本。使用 `/notebooklm use <名稱>` 設定。"
            await client.chat_postMessage(channel=channel_id, text=text)

        elif subcommand == "clear":
            self._config.remove_channel(channel_id)
            await client.chat_postMessage(
                channel=channel_id,
                text=":wastebasket: 已清除此頻道的筆記本設定。",
            )

        else:
            await client.chat_postMessage(
                channel=channel_id,
                text=f":x: 未知指令 `{subcommand}`。輸入 `/notebooklm help` 查看說明。",
            )

    # ------------------------------------------------------------------
    # Bridge pipeline (runs as a background task)
    # ------------------------------------------------------------------

    async def _ask_bridge(
        self,
        channel_id: str,
        question: str,
        thread_ts: str,
        thinking_ts: str,
        client,
    ) -> None:
        """Run the ClaudeNotebookBridge pipeline and update the Slack thread."""
        cfg = self._config.get_channel(channel_id)
        nb_id = cfg.notebook_id if cfg else os.environ.get("NOTEBOOKLM_NOTEBOOK_ID", "")
        nb_title = cfg.notebook_title if cfg else nb_id

        if not nb_id:
            await client.chat_update(
                channel=channel_id,
                ts=thinking_ts,
                blocks=build_error_blocks(
                    "此頻道尚未設定筆記本。\n請使用 `/notebooklm use <名稱>` 選擇一個筆記本。"
                ),
                text="尚未設定筆記本",
            )
            return

        try:
            async with ClaudeNotebookBridge(notebook_id=nb_id) as bridge:
                result = await bridge.ask(question)

            await client.chat_update(
                channel=channel_id,
                ts=thinking_ts,
                blocks=build_answer_blocks(result, nb_title),
                text=result.formatted_answer[:150],
            )

        except AuthError as e:
            logger.warning("Auth error: %s", e)
            await client.chat_update(
                channel=channel_id,
                ts=thinking_ts,
                blocks=build_error_blocks(f"認證已過期：{e}", recoverable=True),
                text="認證錯誤",
            )

        except RateLimitError as e:
            retry_msg = f"（請 {e.retry_after} 秒後再試）" if e.retry_after else ""
            await client.chat_update(
                channel=channel_id,
                ts=thinking_ts,
                blocks=build_error_blocks(f":hourglass: NotebookLM 速率限制。{retry_msg}"),
                text="速率限制",
            )

        except (NetworkError, RPCTimeoutError) as e:
            await client.chat_update(
                channel=channel_id,
                ts=thinking_ts,
                blocks=build_error_blocks(f"網路錯誤，無法連線 NotebookLM：{e}"),
                text="網路錯誤",
            )

        except anthropic.APIError as e:
            await client.chat_update(
                channel=channel_id,
                ts=thinking_ts,
                blocks=build_error_blocks(
                    f"Claude API 錯誤：{e.message}。請確認 ANTHROPIC_API_KEY。"
                ),
                text="Claude API 錯誤",
            )

        except Exception as e:
            logger.error("Unexpected error in _ask_bridge: %s", traceback.format_exc())
            await client.chat_update(
                channel=channel_id,
                ts=thinking_ts,
                blocks=build_error_blocks(f":x: 發生未預期錯誤：{type(e).__name__}: {e}"),
                text="未預期錯誤",
            )

    # ------------------------------------------------------------------
    # Notebook helpers
    # ------------------------------------------------------------------

    async def _list_notebooks(self) -> list[Notebook]:
        """Return cached notebooks or fetch from NotebookLM."""
        cached = self._cache.get()
        if cached is not None:
            return cached

        async with await NotebookLMClient.from_storage() as nlm:
            notebooks = await nlm.notebooks.list()

        self._cache.set(notebooks)
        return notebooks

    async def _resolve_notebook_by_name(self, text: str) -> Notebook | None:
        """Resolve a notebook by exact ID or case-insensitive title substring."""
        notebooks = await self._list_notebooks()
        text_lower = text.lower()

        # Exact ID match first
        for nb in notebooks:
            if nb.id == text:
                return nb

        # Case-insensitive title substring match
        for nb in notebooks:
            if text_lower in nb.title.lower():
                return nb

        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("NOTEBOOKLM_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    required = ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "ANTHROPIC_API_KEY")
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"錯誤：缺少必要的環境變數：{', '.join(missing)}")
        raise SystemExit(1)

    config_path = get_home_dir() / "slack_config.json"
    config = SlackConfig(path=config_path)
    config.load()

    cache = NotebookCache(ttl_seconds=300)
    bot = SlackNotebookBot(config=config, cache=cache)

    print("Slack NotebookLM Bot 啟動中（Socket Mode）…")
    print(f"Config: {config_path}")
    print("按 Ctrl-C 停止")
    asyncio.run(bot.start())


if __name__ == "__main__":
    main()
