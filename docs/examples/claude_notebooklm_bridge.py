"""Claude ↔ NotebookLM Bridge

A two-stage pipeline that uses Claude as an intelligent intermediary:
  1. Claude refines and structures the user's raw question into a focused query.
  2. The refined query is sent to NotebookLM for knowledge retrieval.
  3. Claude formats NotebookLM's raw answer into a clean, readable response.

Prerequisites:
    pip install anthropic
    notebooklm login   # authenticate with Google

Environment:
    ANTHROPIC_API_KEY  – Anthropic API key
    NOTEBOOKLM_NOTEBOOK_ID  – (optional) default notebook ID to query

Usage (script):
    python docs/examples/claude_notebooklm_bridge.py

Usage (library):
    from docs.examples.claude_notebooklm_bridge import ClaudeNotebookBridge

    async with ClaudeNotebookBridge(notebook_id="<id>") as bridge:
        result = await bridge.ask("What are the key takeaways?")
        print(result.formatted_answer)
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field

import anthropic

from notebooklm import NotebookLMClient
from notebooklm.types import AskResult


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class BridgeResult:
    """Full result from the Claude ↔ NotebookLM pipeline."""

    original_question: str
    """The raw question as the user typed it."""

    refined_question: str
    """Claude's structured version of the question sent to NotebookLM."""

    notebooklm_answer: str
    """Raw answer from NotebookLM before formatting."""

    formatted_answer: str
    """Claude's final, formatted answer ready for the user."""

    references: list[dict] = field(default_factory=list)
    """Source references returned by NotebookLM (source_id, cited_text)."""

    conversation_id: str = ""
    """NotebookLM conversation ID — pass to ask() to continue the thread."""


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_REFINE_SYSTEM = """\
You are an expert research assistant that helps users query a knowledge base.

Your task is to rewrite the user's question into a focused, precise query that:
- Clarifies ambiguous terms
- Separates compound questions into distinct parts (use numbered sub-questions if needed)
- Adds context clues that help the knowledge base surface relevant passages
- Stays faithful to the user's original intent — do NOT add new topics

Output only the refined question. No preamble, no explanation."""

_FORMAT_SYSTEM = """\
You are a clear and concise technical writer.

You receive a raw knowledge-base answer and your job is to:
1. Organise the content with Markdown headings if there are multiple distinct topics
2. Highlight key terms in **bold**
3. Use bullet lists for enumerated items
4. Remove redundant sentences and filler phrases
5. Preserve all factual content — do NOT add information that is not in the source answer
6. End with a brief "Summary" section (2-3 sentences) if the answer is longer than 150 words

Output only the formatted answer. No meta-commentary."""


# ---------------------------------------------------------------------------
# Bridge class
# ---------------------------------------------------------------------------

class ClaudeNotebookBridge:
    """Async context manager that connects Claude with a NotebookLM notebook.

    Example::

        async with ClaudeNotebookBridge(notebook_id="abc123") as bridge:
            result = await bridge.ask("Summarise the main arguments")
            print(result.formatted_answer)
    """

    def __init__(
        self,
        notebook_id: str,
        *,
        anthropic_api_key: str | None = None,
        model: str = "claude-opus-4-6",
        notebooklm_timeout: float = 60.0,
    ) -> None:
        self.notebook_id = notebook_id
        self.model = model
        self._anthropic = anthropic.AsyncAnthropic(
            api_key=anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        self._notebooklm_timeout = notebooklm_timeout
        self._nlm_client: NotebookLMClient | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ClaudeNotebookBridge":
        self._nlm_client = await NotebookLMClient.from_storage(
            timeout=self._notebooklm_timeout
        )
        await self._nlm_client.__aenter__()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._nlm_client:
            await self._nlm_client.__aexit__(*exc_info)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ask(
        self,
        question: str,
        *,
        conversation_id: str | None = None,
        source_ids: list[str] | None = None,
    ) -> BridgeResult:
        """Run the full pipeline for a single question.

        Args:
            question: The user's raw question (can be informal / multi-part).
            conversation_id: Continue a previous NotebookLM conversation.
            source_ids: Restrict NotebookLM search to specific source IDs.

        Returns:
            BridgeResult with all intermediate and final outputs.
        """
        if self._nlm_client is None:
            raise RuntimeError("Use 'async with ClaudeNotebookBridge(...) as bridge:'")

        # Step 1 — Claude refines the question
        refined = await self._refine_question(question)

        # Step 2 — NotebookLM answers the refined question
        nlm_result: AskResult = await self._nlm_client.chat.ask(
            self.notebook_id,
            refined,
            conversation_id=conversation_id,
            source_ids=source_ids,
        )

        # Step 3 — Claude formats NotebookLM's answer
        formatted = await self._format_answer(question, nlm_result.answer)

        references = [
            {
                "source_id": ref.source_id,
                "cited_text": ref.cited_text,
                "citation_number": ref.citation_number,
            }
            for ref in nlm_result.references
        ]

        return BridgeResult(
            original_question=question,
            refined_question=refined,
            notebooklm_answer=nlm_result.answer,
            formatted_answer=formatted,
            references=references,
            conversation_id=nlm_result.conversation_id,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _refine_question(self, question: str) -> str:
        """Ask Claude to rewrite the question into a focused query."""
        async with self._anthropic.messages.stream(
            model=self.model,
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=_REFINE_SYSTEM,
            messages=[{"role": "user", "content": question}],
        ) as stream:
            final = await stream.get_final_message()

        return next(
            (block.text for block in final.content if block.type == "text"),
            question,  # fallback: use original if extraction fails
        )

    async def _format_answer(self, original_question: str, raw_answer: str) -> str:
        """Ask Claude to organise and clean up NotebookLM's raw answer."""
        user_content = (
            f"**Original question:** {original_question}\n\n"
            f"**Knowledge-base answer:**\n{raw_answer}"
        )

        async with self._anthropic.messages.stream(
            model=self.model,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=_FORMAT_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            final = await stream.get_final_message()

        return next(
            (block.text for block in final.content if block.type == "text"),
            raw_answer,  # fallback: return raw answer unchanged
        )


# ---------------------------------------------------------------------------
# Interactive demo
# ---------------------------------------------------------------------------

async def interactive_demo(notebook_id: str) -> None:
    """Simple REPL that demonstrates a multi-turn conversation."""
    print("Claude ↔ NotebookLM Bridge — interactive demo")
    print(f"Notebook: {notebook_id}")
    print("Type 'quit' or Ctrl-C to exit.\n")

    conversation_id: str | None = None

    async with ClaudeNotebookBridge(notebook_id=notebook_id) as bridge:
        while True:
            try:
                raw = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye!")
                break

            if raw.lower() in {"quit", "exit", "q"}:
                break
            if not raw:
                continue

            print("\n[Refining question…]")
            result = await bridge.ask(raw, conversation_id=conversation_id)

            # Persist conversation thread across turns
            conversation_id = result.conversation_id

            print(f"\n  Refined query: {result.refined_question}\n")
            print("─" * 60)
            print(result.formatted_answer)

            if result.references:
                print("\nSources cited:")
                for ref in result.references:
                    num = f"[{ref['citation_number']}] " if ref["citation_number"] else ""
                    snippet = (ref["cited_text"] or "")[:80]
                    print(f"  {num}{ref['source_id']} — {snippet}…")

            print("─" * 60 + "\n")


async def single_shot_demo(notebook_id: str) -> None:
    """One-shot example: ask a question and print the result."""
    question = "What are the main topics covered and what are the key takeaways?"

    print(f"Question: {question}\n")

    async with ClaudeNotebookBridge(notebook_id=notebook_id) as bridge:
        result = await bridge.ask(question)

    print(f"Refined query:\n  {result.refined_question}\n")
    print("Formatted answer:")
    print("─" * 60)
    print(result.formatted_answer)
    print("─" * 60)

    if result.references:
        print(f"\n{len(result.references)} source(s) cited.")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    nb_id = os.environ.get("NOTEBOOKLM_NOTEBOOK_ID", "")
    if not nb_id:
        print(
            "Set NOTEBOOKLM_NOTEBOOK_ID to your notebook ID, e.g.:\n"
            "  export NOTEBOOKLM_NOTEBOOK_ID=abc123xyz\n"
            "\n"
            "You can find the ID in the NotebookLM URL:\n"
            "  https://notebooklm.google.com/notebook/abc123xyz\n"
            "\n"
            "Or list your notebooks first:\n"
            "  notebooklm list\n"
        )
        raise SystemExit(1)

    # Use interactive mode if running in a TTY, otherwise single-shot
    import sys

    if sys.stdin.isatty():
        asyncio.run(interactive_demo(nb_id))
    else:
        asyncio.run(single_shot_demo(nb_id))
