import json
import logging
import time

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.llm.usage import build_usage_record, record_llm_usage

logger = logging.getLogger(__name__)

class DeepSeekClient:
    def __init__(self):
        self.llm = init_chat_model(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=0.7,
            max_tokens=2048,
            timeout=settings.deepseek_request_timeout,
        )

    async def chat(self, system_prompt: str, user_message: str, *, stage: str = "deepseek.chat") -> str:
        """Send a chat message and return the text response"""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        started_at = time.perf_counter()
        logger.info(
            "[DeepSeek] request start model=%s stage=%s timeout=%s system_chars=%d user_chars=%d",
            settings.deepseek_model, stage, settings.deepseek_request_timeout, len(system_prompt), len(user_message)
        )
        try:
            response = await self.llm.ainvoke(messages)
        except Exception:
            logger.exception(
                "[DeepSeek] request failed after %.2fs",
                time.perf_counter() - started_at
            )
            raise

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        content = response.content or ""
        usage_record = build_usage_record(
            response=response,
            provider="deepseek",
            model=settings.deepseek_model,
            stage=stage,
            prompt_chars=len(system_prompt)+len(user_message),
            completion_chars=len(content),
            latency_ms=elapsed_ms
        )
        record_llm_usage(usage_record)
        logging.info(
            "[DeepSeek] request finished in %.2fs stage=%s response_char=%d tokens=%d estimated=%s",
            elapsed_ms / 1000, stage, len(content), usage_record.total_tokens, usage_record.estimated
        )
        return str(content)

    async def json_chat(self, system_prompt: str, user_message: str, *, stage="deepseek.json_chat") -> dict:
        """Send a chat message and parse the response as JSON"""
        raw = await self.chat(system_prompt, user_message, stage=stage)
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logging.warning("Failed to parse LLM JSON response: %s", text[:200])
            return {"raw_response": raw}

deepseek_client = DeepSeekClient()