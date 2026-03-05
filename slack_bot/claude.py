"""
Call Claude with tools that query Postgres. Runs tool calls in a loop until Claude responds with text.
"""
import json
from datetime import datetime
from typing import List, Dict, Any

import anthropic

from .config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from . import db


def _system_prompt() -> str:
    """Return a system prompt that includes the current local date and formatting rules."""
    today = datetime.now().date().isoformat()
    return (
        "You are a helpful assistant that answers questions about the user's spending and "
        "transaction history. The data comes from YNAB (You Need A Budget). Amounts in the "
        "tool results are in dollars. "
        f"Today's local date is {today}. When the user asks about relative time periods like "
        "'this month', 'last month', 'last year', or 'last 30 days', interpret them using this "
        "local date and choose explicit calendar date ranges accordingly. "
        "Use the tools to query the database when needed. Be concise and friendly. "
        "When presenting tabular results (e.g. spending by category or by payee), format them as "
        "a plain text table inside a single code block, using aligned columns, NOT markdown "
        "pipe tables. For example:\n"
        "```\n"
        "Category                          Amount\n"
        "--------------------------------  ---------\n"
        "Dining                            $123.45\n"
        "Groceries                         $456.78\n"
        "```\n"
        "Always give totals in the tables. "
    )

TOOLS = [
    {
        "name": "spending_by_category",
        "description": "Get spending summed by category for a date range. Good for 'how much by category' or 'spending by category'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "category_filter": {"type": "string", "description": "Optional filter on category name (partial match)."},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "spending_by_payee",
        "description": "Get spending summed by payee for a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "payee_filter": {"type": "string", "description": "Optional filter on payee name."},
                "limit": {"type": "integer", "description": "Max number of payees to return.", "default": 30},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "total_spending",
        "description": "Get total spending (and transaction count) for a date range. Includes inflows and outflows; negative amounts are outflows.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "recent_transactions",
        "description": "List recent transactions with date, payee, category, amount.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "limit": {"type": "integer", "description": "Max transactions to return.", "default": 20},
                "category": {"type": "string", "description": "Optional filter by category name."},
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "date_range_available",
        "description": "Get the earliest and latest transaction dates in the database. Use this if the user asks what data is available or the range of dates.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def answer_question(question: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": question}]
    max_turns = 5

    for _ in range(max_turns):
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=_system_prompt(),
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if block.type == "text":
                    return block.text
            return "I don't have a response for that."

        # Tool use: collect all tool results for this turn
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = db.run_tool(block.name, **block.input)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

        # Anthropic API requires user messages to have non-empty content.
        # If no tools were requested, stop gracefully instead of sending an empty content list.
        if not tool_results:
            return "I don't have a response for that."

        messages.append({"role": "user", "content": tool_results})

    return "I hit the limit on query steps. Try a simpler question."


def answer_question_with_history(messages: List[Dict[str, Any]]) -> str:
    """
    Same as answer_question but with prior conversation context.
    messages: list of {"role": "user"|"assistant", "content": str} (text only).
    Returns the next assistant reply.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    api_messages = list(messages)
    max_turns = 5

    for _ in range(max_turns):
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=_system_prompt(),
            tools=TOOLS,
            messages=api_messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if block.type == "text":
                    return block.text
            return "I don't have a response for that."

        api_messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = db.run_tool(block.name, **block.input)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})

        if not tool_results:
            return "I don't have a response for that."

        api_messages.append({"role": "user", "content": tool_results})

    return "I hit the limit on query steps. Try a simpler question."
