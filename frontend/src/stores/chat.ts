import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ChatMessage, Citation } from '@/types/chat'
import { chatApi, type Session } from '@/api/chat'

export const useChatStore = defineStore('chat', () => {
  // State
  const messages = ref<ChatMessage[]>([
    {
      id: 'welcome',
      type: 'ai',
      content: '你好！我是你的AI健康助手。\n\n我可以帮你：\n• 解答健康相关问题\n• 分析饮食营养\n• 提供运动建议\n• 评估环境健康风险\n\n今天想先聊哪一项？',
      timestamp: Date.now(),
    }
  ])
  const sessions = ref<Session[]>([])
  const currentSessionId = ref<string | undefined>(undefined)
  const isLoading = ref(false)
  const suggestedQuestions = ref<string[]>([
    '🍎 分析我的饮食',
    '🏃 今日运动建议',
    '😴 改善睡眠质量',
    '🌤️ 空气质量查询',
  ])

  // Getters
  const currentMessages = computed(() => messages.value)
  const currentSession = computed(() =>
    sessions.value.find((s: Session) => s.id === currentSessionId.value)
  )

  // Actions
  async function sendMessage(content: string, attachments?: File[]) {
    if (!content.trim() || isLoading.value) return

    // Add user message
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      type: 'user',
      content,
      timestamp: Date.now(),
      attachments: attachments?.map(f => ({
        type: 'image' as const,
        url: URL.createObjectURL(f),
      })),
    }
    messages.value.push(userMessage)
    isLoading.value = true

    try {
      // Check if we should use streaming
      const useStream = true

      if (useStream) {
        // Create AI message placeholder
        const aiMessageId = `ai-${Date.now()}`
        const aiMessage: ChatMessage = {
          id: aiMessageId,
          type: 'ai',
          content: '',
          timestamp: Date.now(),
          isStreaming: true,
        }
        messages.value.push(aiMessage)

        // Stream response
        await chatApi.sendMessageStream(
          {
            message: content,
            sessionId: currentSessionId.value,
            attachments,
          },
          {
            onContent: (chunk) => {
              const msg = messages.value.find(m => m.id === aiMessageId)
              if (msg) {
                msg.content += chunk
              }
            },
            onCitations: (citations) => {
              const msg = messages.value.find(m => m.id === aiMessageId)
              if (msg) {
                msg.citations = citations
              }
            },
            onSuggestedQuestions: (questions) => {
              suggestedQuestions.value = questions ?? []
            },
            onTraceId: (traceId) => {
              const msg = messages.value.find(m => m.id === aiMessageId)
              if (msg) {
                msg.traceId = traceId
              }
            },
            onDone: () => {
              const msg = messages.value.find(m => m.id === aiMessageId)
              if (msg) {
                msg.isStreaming = false
              }
            },
          }
        )
      } else {
        // Non-streaming response
        const response = await chatApi.sendMessage({
          message: content,
          sessionId: currentSessionId.value,
          attachments,
        })

        const aiMessage: ChatMessage = {
          id: `ai-${Date.now()}`,
          type: 'ai',
          content: response.reply,
          timestamp: Date.now(),
          traceId: response.trace_id,
          citations: response.citations,
        }
        messages.value.push(aiMessage)
        suggestedQuestions.value = response.suggestedQuestions ?? response.suggested_questions ?? []
      }
    } catch (error) {
      console.error('Failed to send message:', error)
      const errorMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        type: 'system',
        content: '发送失败，请稍后重试',
        timestamp: Date.now(),
      }
      messages.value.push(errorMessage)
    } finally {
      isLoading.value = false
    }
  }

  function addMessage(message: ChatMessage) {
    messages.value.push(message)
  }

  function updateMessageContent(id: string, content: string) {
    const msg = messages.value.find(m => m.id === id)
    if (msg) msg.content = content
  }

  function updateMessageCitations(id: string, citations: Citation[]) {
    const msg = messages.value.find(m => m.id === id)
    if (msg) msg.citations = citations
  }

  function finishMessageStreaming(id: string) {
    const msg = messages.value.find(m => m.id === id)
    if (msg) msg.isStreaming = false
  }

  function setSuggestedQuestions(questions: string[]) {
    suggestedQuestions.value = questions
  }

  function clearMessages() {
    messages.value = []
  }

  // 会话管理
  async function loadSessions() {
    try {
      const sessionList = await chatApi.getSessions()
      sessions.value = sessionList
    } catch (error) {
      console.error('Failed to load sessions:', error)
    }
  }

  async function createNewSession() {
    try {
      const newSession = await chatApi.createSession()
      sessions.value.unshift(newSession)
      currentSessionId.value = newSession.id
      clearMessages()
      return newSession
    } catch (error) {
      console.error('Failed to create session:', error)
      throw error
    }
  }

  async function switchSession(sessionId: string) {
    if (sessionId === currentSessionId.value) return

    currentSessionId.value = sessionId
    clearMessages()

    try {
      const history = await chatApi.getChatHistory(sessionId)
      if (history && history.length > 0) {
        messages.value = history.map((msg: any) => ({
          id: `${msg.role}-${msg.timestamp || Date.now()}`,
          type: msg.role === 'user' ? 'user' : 'ai',
          content: msg.content,
          timestamp: msg.timestamp || Date.now(),
          traceId: msg.trace_id || msg.traceId,
        }))
      }
    } catch (error) {
      console.error('Failed to load chat history:', error)
    }
  }

  async function loadSuggestedQuestions() {
    try {
      const questions = await chatApi.getSuggestedQuestions()
      if (questions && questions.length > 0) {
        suggestedQuestions.value = questions
      }
    } catch (error) {
      console.error('Failed to load suggested questions:', error)
    }
  }

  return {
    // State
    messages,
    sessions,
    currentSessionId,
    isLoading,
    suggestedQuestions,
    // Getters
    currentMessages,
    currentSession,
    // Actions
    sendMessage,
    addMessage,
    updateMessageContent,
    updateMessageCitations,
    finishMessageStreaming,
    setSuggestedQuestions,
    clearMessages,
    // Session management
    loadSessions,
    createNewSession,
    switchSession,
    loadSuggestedQuestions,
  }
})
