"""Prompt context assembly with section budgets and trace metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def estimate_tokens(text: str) -> int:
    """Cheap token estimate good enough for budgeting and observability."""
    if not text:
        return 0
    return max(1, round(len(text) / 4))


@dataclass
class ContextSection:
    name: str        # 区块标识，如 "profile"、"rag_docs"
    title: str       # 渲染进 prompt 的标题行
    content: str     # 实际内容
    budget_tokens: int  # 该区块的 token 预算上限
    priority: int = 50 # 优先级，越小越靠前
    compressible: bool = True # 是否允许被截断


class ContextAssembler:
    """Build a prompt context from prioritized, token-budgeted sections."""

    DEFAULT_BUDGETS = {
        "profile": 1200,
        "medium_term_memory": 1200,
        "short_term_memory": 1800,
        "long_term_memory": 1500,
        "health_data": 900,
        "prompt_security": 300,
        "rag_docs": 3000,
        "agent_results": 1500,
        "warnings": 500,
    }

    def __init__(
        self,
        *,
        total_budget_tokens: int = 12000,
        budgets: dict[str, int] | None = None,
    ):
        self.total_budget_tokens = total_budget_tokens
        self.budgets = {**self.DEFAULT_BUDGETS, **(budgets or {})}

    def budget_for(self, name: str) -> int:
        return self.budgets.get(name, 800)

    def assemble(self, sections: list[ContextSection]) -> dict[str, Any]:
        used_total = 0
        rendered: list[str] = []
        section_traces: list[dict[str, Any]] = []

        for section in sorted(sections, key=lambda item: item.priority):
            content = (section.content or "").strip()
            if not content:
                continue

            original_tokens = estimate_tokens(content)
            allowed_tokens = min(section.budget_tokens, max(self.total_budget_tokens - used_total, 0))
            if allowed_tokens <= 0:
                # 如果全局剩余为 0，区块被标记 dropped=True 直接丢弃——前面的区块不会因为后面的大区块而被挤出，但全局超支时后面的区块会被牺牲。
                section_traces.append(
                    {
                        "section": section.name,
                        "title": section.title,
                        "budget_tokens": section.budget_tokens,
                        "original_tokens": original_tokens,
                        "used_tokens": 0,
                        "truncated": True,
                        "dropped": True,
                    }
                )
                continue

            final_content = content
            truncated = False
            if original_tokens > allowed_tokens and section.compressible:
                max_chars = max(120, allowed_tokens * 4)
                final_content = content[:max_chars].rstrip() + "\n...[已按上下文预算截断]"
                truncated = True

            used_tokens = estimate_tokens(final_content)
            used_total += used_tokens
            rendered.append(f"\n{section.title}\n{final_content}")
            section_traces.append(
                {
                    "section": section.name,
                    "title": section.title,
                    "budget_tokens": section.budget_tokens,
                    "original_tokens": original_tokens,
                    "used_tokens": used_tokens,
                    "truncated": truncated,
                    "dropped": False,
                }
            )

        return {
            "context": "\n".join(rendered).strip(),
            "trace": {
                "total_budget_tokens": self.total_budget_tokens,
                "used_tokens": used_total,
                "sections": section_traces,
            },
        }

def budget_profile_for(memory_policy: dict[str, Any] | None, intent: str = "") -> dict[str, int]:
    """Adjust section budgets for the current routing policy."""
    policy = memory_policy or {}
    budgets = dict(ContextAssembler.DEFAULT_BUDGETS)

    scope = policy.get("scope", "")
    budgets["medium_term_memory"] = 1200
    if policy.get("needs_short_term"):
        budgets["short_term_memory"] = 2600 if scope == "short_only" else 2200
    else:
        budgets["short_term_memory"] = 700

    if policy.get("needs_long_term"):
        budgets["long_term_memory"] = 2200
    else:
        budgets["long_term_memory"] = 700

    if not policy.get("needs_rag", True):
        budgets["rag_docs"] = 900
    elif intent in {"exercise", "nutrition", "environment", "multi_domain"}:
        budgets["rag_docs"] = 2600

    return budgets
