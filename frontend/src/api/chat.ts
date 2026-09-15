import { authHeaders, ensureAuthorizedResponse } from './auth'
import { apiUrl } from './client'

export interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp?: string
}

export interface Session {
  id: string
  title: string
  lastMessage: string
  time: string
  messageCount?: number
}

export interface ChatHistoryResponse {
  session_id: string
  messages: Message[]
  total: number
}

export interface StreamRequest {
  message: string
  sessionId?: string
  attachments?: File[]
}

export interface StreamCallbacks {
  onContent?: (chunk: string) => void
  onCitations?: (citations: any[]) => void
  onSuggestedQuestions?: (questions: string[]) => void
  onSessionId?: (sessionId: string) => void
  onSessionTitle?: (sessionTitle: string) => void
  onTraceId?: (traceId: string) => void
  onDone?: () => void
}

export interface SendMessagePayload {
  message: string
  sessionId?: string
  attachments?: File[]
}

export interface SendMessageResponse {
  reply: string
  session_id?: string
  sessionId?: string
  session_title?: string
  sessionTitle?: string
  trace_id?: string
  citations?: any[]
  suggested_questions?: string[]
  suggestedQuestions?: string[]
}

export interface SuggestedQuestionFeedbackPayload {
  question: string
  action?: 'shown' | 'clicked' | 'dismissed'
  source?: string
  context?: Record<string, unknown>
}

function buildFormData(payload: SendMessagePayload): FormData {
  const formData = new FormData()
  formData.append('message', payload.message)
  if (payload.sessionId) {
    formData.append('session_id', payload.sessionId)
  }
  for (const file of payload.attachments || []) {
    formData.append('attachments', file)
  }
  return formData
}

// 发送消息（非流式）
export async function sendMessage(payload: SendMessagePayload): Promise<SendMessageResponse> {
  const formData = buildFormData(payload)

  const response = await fetch(apiUrl('/api/v1/chat/send'), {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  })

  if (!ensureAuthorizedResponse(response)) {
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '发送消息失败')
  }

  return response.json()
}

export async function sendMessageStream(
  payload: StreamRequest,
  callbacks: StreamCallbacks = {},
) {
  const formData = buildFormData(payload)

  const response = await fetch(apiUrl('/api/v1/chat/stream'), {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  })

  if (!ensureAuthorizedResponse(response)) {
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('No response body')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''

    for (const event of events) {
      const dataLine = event
        .split('\n')
        .find((line) => line.startsWith('data:'))

      if (!dataLine) continue

      const payloadText = dataLine.slice(5).trim()
      if (!payloadText) continue

      const data = JSON.parse(payloadText)
      if (data.session_id) callbacks.onSessionId?.(data.session_id)
      if (data.session_title) callbacks.onSessionTitle?.(data.session_title)
      if (data.content) callbacks.onContent?.(data.content)
      if (data.citations) callbacks.onCitations?.(data.citations)
      if (data.suggestedQuestions) callbacks.onSuggestedQuestions?.(data.suggestedQuestions)
      if (data.trace_id) callbacks.onTraceId?.(data.trace_id)
      if (data.error) throw new Error(data.error)
      if (data.done) callbacks.onDone?.()
    }
  }
}

// 获取会话列表
export async function getSessions(): Promise<Session[]> {
  try {
    const response = await fetch(apiUrl('/api/v1/chat/sessions'), {
      method: 'GET',
      headers: {
        ...authHeaders(),
        'Accept': 'application/json',
      },
    })

    if (!ensureAuthorizedResponse(response)) {
      throw new Error('登录已过期，请重新登录')
    }

    if (!response.ok) {
      const text = await response.text()
      throw new Error(text || '获取会话列表失败')
    }

    const data = await response.json()
    return data.sessions || []
  } catch (error) {
    console.warn('获取会话列表失败:', error)
    return []
  }
}

// 获取聊天历史
export async function getChatHistory(sessionId: string): Promise<Message[]> {
  try {
    const response = await fetch(
      apiUrl(`/api/v1/chat/history?session_id=${sessionId}&limit=50`),
      {
        method: 'GET',
        headers: {
          ...authHeaders(),
          'Accept': 'application/json',
        },
      }
    )

    if (!ensureAuthorizedResponse(response)) {
      return []
    }

    if (!response.ok) {
      console.warn('获取聊天历史失败')
      return []
    }

    const data = await response.json()
    return data.messages || []
  } catch (error) {
    console.warn('获取聊天历史失败:', error)
    return []
  }
}

// 创建新会话
export async function createSession(): Promise<Session> {
  try {
    const response = await fetch(apiUrl('/api/v1/chat/session'), {
      method: 'POST',
      headers: {
        ...authHeaders(),
        'Accept': 'application/json',
      },
    })

    if (!ensureAuthorizedResponse(response)) {
      throw new Error('登录已过期，请重新登录')
    }

    if (!response.ok) {
      throw new Error('创建会话失败')
    }

    const data = await response.json()
    return {
      id: data.id || data.session_id,
      title: data.title || '新对话',
      lastMessage: '',
      time: '刚刚',
    }
  } catch (error) {
    console.warn('创建会话失败:', error)
    throw error
  }
}

// 获取推荐问题
export async function getSuggestedQuestions(): Promise<string[]> {
  try {
    const response = await fetch(apiUrl('/api/v1/chat/suggestions'), {
      method: 'GET',
      headers: {
        ...authHeaders(),
        'Accept': 'application/json',
      },
    })

    if (!ensureAuthorizedResponse(response)) {
      return getMockSuggestions()
    }

    if (!response.ok) {
      return getMockSuggestions()
    }

    const data = await response.json()
    return data.suggestions || []
  } catch (error) {
    return getMockSuggestions()
  }
}

export async function recordSuggestedQuestionFeedback(
  payload: SuggestedQuestionFeedbackPayload,
): Promise<void> {
  try {
    const response = await fetch(apiUrl('/api/v1/chat/suggestions/feedback'), {
      method: 'POST',
      headers: {
        ...authHeaders(),
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        action: 'clicked',
        ...payload,
      }),
    })

    ensureAuthorizedResponse(response)
  } catch (error) {
    console.warn('记录推荐问题反馈失败:', error)
  }
}

// Mock数据 - 推荐问题
function getMockSuggestions(): string[] {
  return [
    '🍎 分析我的饮食',
    '🏃 今日运动建议',
    '😴 改善睡眠质量',
    '🌤️ 空气质量查询',
    '💊 维生素补充建议',
    '🥤 每日饮水量计算',
  ]
}

export default {
  sendMessage,
  sendMessageStream,
  getSessions,
  getChatHistory,
  createSession,
  getSuggestedQuestions,
  recordSuggestedQuestionFeedback,
}

export const chatApi = {
  sendMessage,
  sendMessageStream,
  getSessions,
  getChatHistory,
  createSession,
  getSuggestedQuestions,
  recordSuggestedQuestionFeedback,
}
