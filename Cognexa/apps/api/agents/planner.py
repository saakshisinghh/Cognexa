"""
apps/api/agents/planner.py

Phase 5 — Agent Planner.

Runs BEFORE every agent execution to:
    1. Understand the user's goal
    2. Break it into discrete tasks
    3. Choose which tools are needed, in what order
    4. Estimate a starting confidence for the plan itself
    5. Emit a structured execution plan consumed by the agent's
       LangGraph retriever / graph-query / tool-executor nodes

Uses the EXISTING OpenAI-compatible LLM gateway (apps/api/services/
llm_gateway.py) — no second LLM client is introduced. Structured output
is obtained via constrained JSON prompting + a tolerant parser, rather
than provider-specific function calling, so this works identically
against local Ollama models and hosted OpenAI-compatible endpoints.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from apps.api.services.llm_gateway import complete_response, LLMUnavailableError

logger = logging.getLogger("indusmind.agents.planner")


@dataclass
class PlannedTask:
    task: str
    tool: Optional[str] = None
    tool_input: dict = field(default_factory=dict)
    rationale: str = ""


@dataclass
class ExecutionPlan:
    goal_summary: str
    task_type: str
    tasks: list[PlannedTask]
    estimated_confidence: float
    raw_plan: dict


_PLAN_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Tolerant JSON extraction — local LLMs frequently wrap JSON in
    markdown fences or add a sentence of preamble before/after."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _PLAN_JSON_RE.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise ValueError(f"Planner LLM did not return parseable JSON: {text[:200]!r}")


def _build_planner_prompt(goal: str, agent_name: str, available_tools: list[dict], context: dict) -> list[dict]:
    tools_desc = "\n".join(
        f"- {t['name']}: {t['description']} (input: {t['input_schema']})" for t in available_tools
    )
    system = (
        f"You are the task planner for the {agent_name}, part of the INDUS MIND industrial AI platform.\n"
        "Given a user goal, produce a JSON execution plan ONLY — no prose before or after.\n\n"
        f"Available tools:\n{tools_desc}\n\n"
        "Respond with EXACTLY this JSON shape:\n"
        "{\n"
        '  "goal_summary": "<one sentence restating the goal>",\n'
        '  "task_type": "<short classification, e.g. root_cause_analysis>",\n'
        '  "tasks": [\n'
        '    {"task": "<description>", "tool": "<tool name or null>", '
        '"tool_input": {}, "rationale": "<why this task/tool>"}\n'
        "  ],\n"
        '  "estimated_confidence": 0.0\n'
        "}\n"
        "Keep the plan to 2-6 tasks, ordered by execution sequence. "
        "estimated_confidence is your own confidence (0.0-1.0) that this plan will fully "
        "satisfy the goal given the available tools."
    )
    user = f"GOAL: {goal}\nCONTEXT: {json.dumps(context, default=str)}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


_FALLBACK_PLAN = {
    "goal_summary": "",
    "task_type": "general",
    "tasks": [
        {"task": "Run hybrid retrieval against the goal text", "tool": "rag_retrieval",
         "tool_input": {}, "rationale": "Fallback plan — LLM planning unavailable."},
    ],
    "estimated_confidence": 0.3,
}


async def generate_plan(
    goal: str,
    agent_name: str,
    available_tools: list[dict],
    context: Optional[dict] = None,
) -> ExecutionPlan:
    """
    Produces an ExecutionPlan for the given goal. Degrades to a safe
    single-task fallback plan (full RAG retrieval) if the LLM is
    unavailable or returns unparseable output — planning failures must
    never crash an agent execution outright.
    """
    context = context or {}
    messages = _build_planner_prompt(goal, agent_name, available_tools, context)

    try:
        raw_text, _in_tok, _out_tok = await complete_response(messages)
        plan_dict = _extract_json(raw_text)
    except (LLMUnavailableError, ValueError) as exc:
        logger.warning("planner_llm_failed agent=%s error=%s — using fallback plan", agent_name, exc)
        plan_dict = dict(_FALLBACK_PLAN)
        plan_dict["goal_summary"] = goal[:200]

    tasks = [
        PlannedTask(
            task=t.get("task", ""),
            tool=t.get("tool"),
            tool_input=t.get("tool_input") or {},
            rationale=t.get("rationale", ""),
        )
        for t in plan_dict.get("tasks", [])
    ]
    if not tasks:
        tasks = [PlannedTask(task="Run hybrid retrieval against the goal text", tool="rag_retrieval")]

    valid_tool_names = {t["name"] for t in available_tools}
    for task in tasks:
        if task.tool and task.tool not in valid_tool_names:
            logger.warning("planner_selected_unknown_tool tool=%s — dropping tool binding", task.tool)
            task.tool = None

    return ExecutionPlan(
        goal_summary=plan_dict.get("goal_summary", goal[:200]),
        task_type=plan_dict.get("task_type", "general"),
        tasks=tasks,
        estimated_confidence=float(plan_dict.get("estimated_confidence", 0.5)),
        raw_plan=plan_dict,
    )
