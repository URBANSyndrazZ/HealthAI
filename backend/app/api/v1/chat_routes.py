"""Authenticated chat API routes"""
import json
import logging
import re
import time
import asyncio
import uuid
from typing import Literal, Any, AsyncGenerator

from fastapi import APIRouter, Request, HTTPException, status, Form, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.agents.health_advisor import HealthAdvisorState
from app.agents.health_advisor.nodes import load_context, check_safety, urgent_reply, post_process, classify_intent, \
    memory_route, retrieve_memory, plan_tasks, aggregate_results, rag_retrieve, generate_response, dispatch_agents
from app.api.deps import get_current_user, get_db
from app.core.observability import get_trace_id
from app.core.time import utc_now_naive
from app.llm.deepseek import deepseek_client
from app.memory.medium_term import medium_term_memory
from app.models import ChatSession, ChatMessage, User
from app.models.database import async_session
from app.memory.short_term import short_term_memory
from app.services.suggested_questions import suggested_question_service

logger = logging.getLogger(__name__)

router = APIRouter()

class SendMessageResponse(BaseModel):
    reply: str
    session_id: str
    session_title: str
    message_id: str
    trace_id: str
    citations: list[dict] = []
    suggested_questions: list[str] = []
    safety_flag: dict | None = None
    intent: str | None = None


class SuggestedQuestionFeedbackRequest(BaseModel):
    question: str
    action: Literal["shown", "clicked", "dismissed"] = "clicked"
    source: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)

async def _extra_message_payload(
    request: Request,
    from_message: str | None,
    from_session_id: str | None
) -> tuple[str, str | None]:
    """Support both legacy form ports and JSON posts used by API clients"""
    if from_message:
        return from_message, from_session_id

    if request.headers.get("content-type", "").startswith("application/json"):
        payload = await request.json()
        return (
            payload.get("message", ""),
            payload.get("session_id") or payload.get("sessionId")
        )
    return "", from_session_id

def _compact_session_title(content: str | None, max_len: int = 16) -> str:
    """Create a stable, concise title from the user's first question."""
    if not content:
        return "新对话"

    text = re.sub(r"\s+", " ", content).strip()
    text = re.sub(r"^[#>*\-\d\.\s]+", "", text)
    text = re.sub(
        r"^(请问|请帮我|帮我|麻烦|能不能|可以|我想|想问一下|咨询一下)[，,：:\s]*",
        "",
        text,
    )
    text = text.strip("。！？?!.，,；;：:、\"'“”‘’ ")
    if not text:
        return "新对话"

    topic_title = _infer_session_topic(text)
    if topic_title:
        return topic_title

    if len(text) <= max_len:
        return text
    return f"{text[:max_len]}..."

def _infer_session_topic(text: str) -> str | None:
    if any(keyword in text for keyword in ("睡眠", "失眠", "入睡", "早醒", "晚睡", "熬夜", "作息")):
        if any(keyword in text for keyword in ("作息", "晚睡", "熬夜")):
            return "睡眠作息调整"
        return "睡眠状态分析"

    if any(keyword in text for keyword in ("饮食", "早餐", "午餐", "晚餐", "营养", "热量", "蛋白", "减脂", "控糖")):
        return "饮食营养分析"

    if any(keyword in text for keyword in ("运动", "跑步", "步数", "健身", "锻炼", "训练", "户外跑")):
        return "运动计划建议"

    if any(keyword in text for keyword in ("心率", "血压", "血糖", "体检", "指标", "胆固醇", "尿酸")):
        return "健康指标解读"

    if any(keyword in text for keyword in ("空气", "天气", "紫外线", "过敏", "温度", "湿度", "雾霾")):
        return "环境健康建议"

    if any(keyword in text for keyword in ("数据", "趋势", "最近", "这周", "本周", "分析")):
        return "健康数据分析"

    return None

async def _get_session_title(
    db: AsyncSession,
    session_id: str,
    fallback_message: str | None = None
) -> str:
    first_user = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id==session_id)
            .where(ChatMessage.role=="user")
            .order_by(ChatMessage.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return _compact_session_title(first_user.content if first_user else fallback_message)

async def _process_state(state: HealthAdvisorState) -> HealthAdvisorState:
    """Run the HealthAdvisor graph steps explicitly for route-level testability."""
    trace_id = state.get("trace_id") or get_trace_id() or str(uuid.uuid4())
    state["trace_id"] = trace_id

    async def run_stage(stage_name: str, func, *, needs_db: bool = False) -> HealthAdvisorState:
        started_at = time.perf_counter()
        logger.info(
            "[chat_pipeline] trace=%s stage=%s start session=%s user=%s message=%s",
            trace_id,
            stage_name,
            state.get("session_id", ""),
            state.get("user_id", ""),
            state.get("user_message", "")[:80],
        )
        try:
            if needs_db:
                async with async_session() as db:
                    result = await func(state, db)
            else:
                result = await func(state)
        except Exception:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            trace = dict(state.get("agent_trace") or {})
            trace[stage_name] = {"status": "error", "elapsed_ms": elapsed_ms}
            state["agent_trace"] = trace
            logger.exception(
                "[chat_pipeline] trace=%s stage=%s failed session=%s after %.2fs",
                trace_id,
                stage_name,
                state.get("session_id", ""),
                time.perf_counter() - started_at,
            )
            raise

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        prior_trace = dict(state.get("agent_trace") or {})
        prior_trace[stage_name] = {"status": "ok", "elapsed_ms": elapsed_ms}
        result["agent_trace"] = {**(result.get("agent_trace") or {}), **prior_trace}
        result["trace_id"] = trace_id
        logger.info(
            "[chat_pipeline] trace=%s stage=%s done session=%s elapsed=%.2fs",
            trace_id,
            stage_name,
            state.get("session_id", ""),
            time.perf_counter() - started_at,
        )
        return result

    state = await run_stage("load_context", load_context, needs_db=True)
    state = await run_stage("check_safety", check_safety)
    safety_flag = state.get("safety_flag") or {}
    if safety_flag.get("is_urgent"):
        state = await run_stage("urgent_reply", urgent_reply)
        return await run_stage("post_process", post_process, needs_db=True)

    state = await run_stage("classify_intent", classify_intent)
    state = await run_stage("memory_route", memory_route)
    state = await run_stage("retrieve_memory", retrieve_memory, needs_db=True)
    state = await run_stage("plan_tasks", plan_tasks)
    if state.get("sub_tasks"):
        state = await run_stage("dispatch_agents", dispatch_agents)
        state = await run_stage("aggregate_results", aggregate_results)
    if (state.get("memory_policy") or {}).get("needs_rag", True):
        state = await run_stage("rag_retrieve", rag_retrieve)
    state = await run_stage("generate_response", generate_response)
    return await run_stage("post_process", post_process, needs_db=True)


async def _get_or_create_session(
    db: AsyncSession,
    user_id: str,
    session_id: str | None
) -> ChatSession:
    if session_id:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return session

    session = ChatSession(user_id=user_id)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

async def _save_chat_turn(
    db: AsyncSession,
    session_id: str,
    user_message: str,
    result: HealthAdvisorState,
    user_id: str | None = None,
) -> ChatMessage:
    user_msg = ChatMessage(session_id=session_id, role="user", content=user_message)
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=result.get("response", ""),
        citations=result.get("citations", []),
        suggested_questions=result.get("suggested_questions", [])
    )
    db.add(user_msg)
    db.add(assistant_msg)

    session = await db.get(ChatSession, session_id)
    if session:
        session.updated_at = utc_now_naive()

    await db.commit()
    await db.refresh(assistant_msg)
    if user_id:
        try:
            await short_term_memory.add_turn(
                user_id,
                session_id,
                user_message,
                result.get("response", ""),
                message_id=assistant_msg.id,
                created_at=assistant_msg.created_at.isoformat() if assistant_msg.created_at else None,
            )
        except Exception:
            logger.exception("Failed to update short-term memory after database persistence")

    try:
        medium_term_memory.schedule_update(session_id)
    except Exception:
        logger.exception("Failed to schedule medium-term memory after database persistence")
    return assistant_msg

def _message_to_dict(message: ChatMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "attachments": message.attachments,
        "citations": message.citations,
        "suggested_questions": message.suggested_questions,
        "created_at": message.created_at.isoformat() if message.created_at else None
    }

@router.post("/send", response_model=SendMessageResponse)
async def send_message(
    request: Request,
    message: str | None = None,
    session_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send a message and get an authenticated, persisted response"""
    try:
        message, session_id = await _extra_message_payload(request, message, session_id)
        if not message:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="message is required")

        session = await _get_or_create_session(db, current_user.id, session_id)
        state = HealthAdvisorState(
            user_message=message,
            user_id=current_user.id,
            session_id=session.id,
            trace_id=getattr(request.state, "trace_id", get_trace_id())
        )
        result = await _process_state(state)
        assistant_msg = await _save_chat_turn(db, session.id, message, result, current_user.id)
        session_title = await _get_session_title(db, session.id, message)

        return SendMessageResponse(
            reply=result.get("response", ""),
            session_id=session.id,
            session_title=session_title,
            message_id=assistant_msg.id,
            trace_id=result.get("trace_id", getattr(request.state, "trace_id")),
            citations=result.get("citations", []),
            suggested_questions=result.get("suggested_questions", []),
            safety_flag=result.get("safety_flag", None),
            intent=result.get("intent", None)
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error in send_message")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

async def stream_response(
    message: str,
    session_id: str | None,
    user_id: str,
    trace_id: str,
) -> AsyncGenerator[str, None]:
    """Stream response using SSE and persist the completed chat turn."""
    try:
        async with async_session() as db:
            session = await _get_or_create_session(db, user_id, session_id)

        state = HealthAdvisorState(
            user_message=message,
            user_id=user_id,
            session_id=session.id,
            trace_id=trace_id,
        )

        yield f"data: {json.dumps({'status': 'processing', 'stage': 'started', 'session_id': session.id, 'trace_id': trace_id})}\n\n"

        started_at = time.perf_counter()
        result = await _process_state(state)
        logger.info(
        "[chat_pipeline] trace=%s stream completed session=%s elapsed=%.2fs",
        trace_id,
        session.id,
        time.perf_counter() - started_at,
        )

        response = result.get("response", "")
        safety_flag = result.get("safety_flag", None)
        if safety_flag:
            yield f"data: {json.dumps({'safety_flag': safety_flag}, ensure_ascii=False)}\n\n"

        chunk_size = 2
        for index in range(0, len(response), chunk_size):
            chunk = response[index:index + chunk_size]
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.012)

        citations = result.get("citations", [])
        if citations:
            yield f"data: {json.dumps({'citations': citations}, ensure_ascii=False)}\n\n"

        suggested_questions = result.get("suggested_questions", [])
        if suggested_questions:
            yield f"data: {json.dumps({'suggestedQuestions': suggested_questions}, ensure_ascii=False)}\n\n"

        async with async_session() as db:
            assistant_msg = await _save_chat_turn(db, session.id, message, result, user_id)
            session_title = await _get_session_title(db, session.id, message)

        done_payload = {
            "done": True,
            "session_id": session.id,
            "session_title": session_title,
            "message_id": assistant_msg.id,
            "trace_id": trace_id
        }
        yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

    except Exception as exc:
        logger.exception("Error in stream_response")
        yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

@router.post("/stream")
async def stream_message(
    request: Request,
    message: str = Form(...),
    session_id: str | None = Form(None),
    current_user: User = Depends(get_current_user)
):
    """Send a message and stream the authenticated response using SSE."""
    trace_id = getattr(request.state, "trace_id", get_trace_id())
    return StreamingResponse(
        stream_response(message, session_id, current_user.id, trace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@router.get("/sessions")
async def get_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List current user's chat sessions"""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id==current_user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = []
    for session in result.scalars().all():
        count = (
            await db.execute(
                select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id==session.id)
            )
        ).scalar_one()
        last = (
            await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id==session.id)
                .order_by(ChatMessage.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        sessions.append(
            {
                "id": session.id,
                "title": await _get_session_title(db, session.id),
                "lastMessage": last.content if last else "",
                "time": session.updated_at.isoformat() if session.updated_at else "",
                "messageCount": count
            }
        )
    return {"sessions": sessions}

@router.get("/history")
async def get_chat_history(
    session_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current user's chat history for a session"""
    session = await _get_or_create_session(db, current_user.id, session_id)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id==session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
    )
    messages = [_message_to_dict(message) for message in result.scalars().all()]
    return {"session_id": session.id, "messages": messages, "total": len(messages)}

@router.get("/history/{session_id}")
async def get_chat_history_by_id(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await get_chat_history(session_id=session_id, limit=50, db=db, current_user=current_user)

@router.post("/session")
async def create_session(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new persisted chat session."""
    session = await _get_or_create_session(db, current_user.id, None)
    return {
        "id": session.id,
        "session_id": session.id,
        "title": "新对话",
        "lastMessage": "",
        "time": session.created_at.isoformat() if session.created_at else "",
    }

@router.get("/suggestions")
@router.post("/suggestions")
async def get_suggestions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get suggested questions for the current user."""
    suggestions = await suggested_question_service.get_home_suggestions(db, current_user.id)
    return {"suggestions": suggestions}

@router.post("/suggestions/feedback")
async def record_suggested_question_feedback(
    payload: SuggestedQuestionFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record suggested question impression/clicks for later ranking optimization."""
    if not payload.question.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="question is required.")

    feedback = await suggested_question_service.record_feedback(
        db,
        current_user.id,
        question=payload.question,
        action=payload.action,
        source=payload.source,
        context=payload.context
    )
    return {"id": feedback.id, "status": "ok"}
