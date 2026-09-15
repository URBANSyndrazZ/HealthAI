<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { authHeaders, ensureAuthorizedResponse } from '@/api/auth'
import { apiUrl } from '@/api/client'
import { chatApi, type Session } from '@/api/chat'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ breaks: true, gfm: true })

function renderMarkdown(content: string): string {
  if (!content) return ''
  const rawHtml = marked.parse(content) as string
  return DOMPurify.sanitize(rawHtml)
}

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
  isStreaming?: boolean
  citations?: any[]
  traceId?: string
}

function citationTitle(cite: any, index: number) {
  if (typeof cite === 'string') return `资料${index + 1}`
  return cite?.title || cite?.label || `资料${index + 1}`
}

function citationSource(cite: any) {
  if (typeof cite === 'string') return ''
  return cite?.source || ''
}

function citationContent(cite: any) {
  if (typeof cite === 'string') return cite
  return cite?.content || cite?.snippet || ''
}

function citationMeta(cite: any) {
  if (!cite || typeof cite === 'string') return ''
  const metadata = cite.metadata || {}
  const parts = [
    cite.label,
    metadata.category,
    metadata.topic,
    metadata.source_type,
  ].filter(Boolean)
  return parts.join(' · ')
}

const message = ref('')
const messages = ref<Message[]>([])
const loading = ref(false)
const sessionsLoading = ref(false)
const chatArea = ref<HTMLElement>()
const currentSessionId = ref<string>()
const showSidebar = ref(false)
const sessions = ref<Session[]>([])
const suggestedQuestionSource = ref<'home' | 'followup'>('home')

const suggestedQuestions = ref([
  '分析一下我最近的睡眠状态',
  '根据今天的步数给我运动建议',
  '帮我看看这周饮食是否均衡',
  '今天适合户外跑步吗',
])

const capabilityCards = [
  { title: '健康问答', desc: '结合你的日常记录，给出更贴近个人状态的建议。', icon: '问' },
  { title: '趋势分析', desc: '围绕步数、睡眠、心率等数据快速发现变化。', icon: '析' },
  { title: '健康提醒', desc: '用更轻量的方式帮助你坚持长期健康习惯。', icon: '护' },
]

function mapHistoryMessage(msg: any): Message {
  return {
    role: msg.role === 'user' ? 'user' : msg.role === 'system' ? 'system' : 'assistant',
    content: msg.content || '',
    citations: msg.citations || [],
    traceId: msg.trace_id || msg.traceId,
  }
}

async function loadSessions(selectFirst = true) {
  sessionsLoading.value = true
  try {
    const list = await chatApi.getSessions()
    sessions.value = list

    const firstSession = list[0]
    if (selectFirst && firstSession && !currentSessionId.value) {
      await switchSession(firstSession.id)
    }
  } finally {
    sessionsLoading.value = false
  }
}

async function createNewSession() {
  try {
    const newSession = await chatApi.createSession()
    sessions.value.unshift(newSession)
    currentSessionId.value = newSession.id
    messages.value = []
    await loadSuggestedQuestions()
    showSidebar.value = false
  } catch (e: any) {
    messages.value.push({ role: 'assistant', content: `[错误] ${e.message || '创建会话失败'}` })
  }
}

async function switchSession(sessionId: string) {
  currentSessionId.value = sessionId
  messages.value = []
  showSidebar.value = false
  loading.value = true

  try {
    const history = await chatApi.getChatHistory(sessionId)
    messages.value = history.map(mapHistoryMessage)
    scrollToBottom()
  } catch (e: any) {
    messages.value.push({ role: 'assistant', content: `[错误] ${e.message || '加载聊天历史失败'}` })
  } finally {
    loading.value = false
  }
}

function toggleSidebar() {
  showSidebar.value = !showSidebar.value
}

function scrollToBottom() {
  nextTick(() => {
    if (chatArea.value) {
      chatArea.value.scrollTop = chatArea.value.scrollHeight
    }
  })
}

function formatSessionTime(value?: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour

  if (diffMs >= 0 && diffMs < minute) return '刚刚'
  if (diffMs >= 0 && diffMs < hour) return `${Math.floor(diffMs / minute)}分钟前`
  if (diffMs >= 0 && diffMs < day) return `${Math.floor(diffMs / hour)}小时前`

  const month = String(date.getMonth() + 1).padStart(2, '0')
  const dayOfMonth = String(date.getDate()).padStart(2, '0')
  return `${month}-${dayOfMonth}`
}

async function sendMessage() {
  if (!message.value.trim() || loading.value) return

  messages.value.push({ role: 'user', content: message.value })
  const userMsg = message.value
  message.value = ''
  suggestedQuestions.value = []
  loading.value = true
  scrollToBottom()

  try {
    const aiMessage: Message = {
      role: 'assistant',
      content: '',
      isStreaming: true,
    }
    messages.value.push(aiMessage)
    await streamResponse(userMsg, aiMessage)
  } catch (e: any) {
    messages.value.pop()
    messages.value.push({ role: 'assistant', content: `[错误] ${e.message}` })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

async function streamResponse(userMsg: string, aiMessage: Message) {
  const formData = new FormData()
  formData.append('message', userMsg)
  if (currentSessionId.value) {
    formData.append('session_id', currentSessionId.value)
  }

  const res = await fetch(apiUrl('/api/v1/chat/stream'), {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  })

  if (!ensureAuthorizedResponse(res)) {
    throw new Error('登录已过期，请重新登录')
  }

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`)
  }

  const reader = res.body?.getReader()
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

      if (data.session_id) {
        currentSessionId.value = data.session_id
      }

      if (data.session_title && data.session_id) {
        const session = sessions.value.find((item) => item.id === data.session_id)
        if (session) {
          session.title = data.session_title
          session.lastMessage = aiMessage.content
        } else {
          sessions.value.unshift({
            id: data.session_id,
            title: data.session_title,
            lastMessage: aiMessage.content,
            time: '刚刚',
          })
        }
      }

      if (data.content) {
        aiMessage.content += data.content
        scrollToBottom()
      }

      if (data.citations) {
        aiMessage.citations = data.citations
      }

      if (data.suggestedQuestions) {
        setSuggestedQuestions(data.suggestedQuestions, 'followup')
      }

      if (data.trace_id) {
        aiMessage.traceId = data.trace_id
      }

      if (data.error) {
        throw new Error(data.error)
      }

      if (data.done) {
        aiMessage.isStreaming = false
      }
    }
  }

  aiMessage.isStreaming = false
  await loadSessions(false)
}

async function loadSuggestedQuestions() {
  try {
    const questions = await chatApi.getSuggestedQuestions()
    setSuggestedQuestions(questions, 'home')
  } catch {
    // The API layer already falls back; keep existing questions if something unexpected happens.
  }
}

function setSuggestedQuestions(questions: string[], source: 'home' | 'followup') {
  suggestedQuestions.value = (questions || []).filter(Boolean).slice(0, 4)
  suggestedQuestionSource.value = source
  recordSuggestedQuestionsFeedback('shown', suggestedQuestions.value)
}

function suggestionFeedbackContext() {
  return {
    sessionId: currentSessionId.value,
    messageCount: messages.value.length,
  }
}

function recordSuggestedQuestionsFeedback(
  action: 'shown' | 'clicked' | 'dismissed',
  questions: string[],
) {
  for (const question of questions) {
    void chatApi.recordSuggestedQuestionFeedback({
      question,
      action,
      source: suggestedQuestionSource.value,
      context: suggestionFeedbackContext(),
    })
  }
}

async function useSuggestedQuestion(question: string) {
  void chatApi.recordSuggestedQuestionFeedback({
    question,
    action: 'clicked',
    source: suggestedQuestionSource.value,
    context: suggestionFeedbackContext(),
  })
  message.value = question
  await sendMessage()
}

function dismissSuggestedQuestion(question: string) {
  suggestedQuestions.value = suggestedQuestions.value.filter((item) => item !== question)
  void chatApi.recordSuggestedQuestionFeedback({
    question,
    action: 'dismissed',
    source: suggestedQuestionSource.value,
    context: suggestionFeedbackContext(),
  })
}

onMounted(async () => {
  await loadSessions()
  await loadSuggestedQuestions()
})
</script>

<template>
  <div class="home-view">
    <aside class="sidebar" :class="{ open: showSidebar }">
      <div class="sidebar-header">
        <div class="sidebar-brand">
          <img src="/health-logo.svg" alt="AI健康助手" />
          <div>
            <strong>AI健康助手</strong>
            <p>健康对话中心</p>
          </div>
        </div>
        <button class="new-chat-btn" @click="createNewSession">
          <span>+</span>
          新建对话
        </button>
      </div>

      <div class="session-list">
        <div v-if="sessionsLoading" class="session-empty">正在加载历史对话...</div>
        <div v-else-if="sessions.length === 0" class="session-empty">暂无历史对话</div>
        <div
          v-for="session in sessions"
          :key="session.id"
          :class="['session-item', { active: currentSessionId === session.id }]"
          @click="switchSession(session.id)"
        >
          <div class="session-icon">健</div>
          <div class="session-info">
            <div class="session-title">{{ session.title }}</div>
            <div class="session-preview">{{ session.lastMessage }}</div>
            <div class="session-time">{{ formatSessionTime(session.time) }}</div>
          </div>
        </div>
      </div>
    </aside>

    <div v-if="showSidebar" class="sidebar-overlay" @click="toggleSidebar"></div>

    <section class="conversation-panel">
      <div class="conversation-topbar">
        <button class="menu-btn" @click="toggleSidebar" aria-label="打开会话列表">
          <span></span>
          <span></span>
          <span></span>
        </button>

        <div class="topbar-copy">
          <h1>智能健康对话</h1>
          <p>围绕睡眠、饮食、运动和环境，为你提供日常健康建议。</p>
        </div>
      </div>

      <main class="chat-area" ref="chatArea">
        <div v-if="messages.length === 0" class="empty-state">
          <div class="empty-hero">
            <img src="/health-logo.svg" alt="AI健康助手" class="hero-logo" />
            <div>
              <span class="hero-badge">AI健康助手</span>
              <h2>从日常数据出发，帮你把健康建议变得更具体</h2>
              <p>你可以直接询问睡眠、饮食、运动或环境问题，也可以结合健康档案做个性化分析。</p>
            </div>
          </div>

          <div class="capability-grid">
            <article v-for="item in capabilityCards" :key="item.title" class="capability-card">
              <div class="capability-icon">{{ item.icon }}</div>
              <h3>{{ item.title }}</h3>
              <p>{{ item.desc }}</p>
            </article>
          </div>
        </div>

        <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.role]">
          <div class="bubble">
            <div v-if="msg.role === 'assistant'" class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
            <template v-else>{{ msg.content }}</template>
            <span v-if="msg.isStreaming" class="typing-indicator">
              <span class="dot"></span>
              <span class="dot"></span>
              <span class="dot"></span>
            </span>
          </div>
          <div v-if="msg.citations && msg.citations.length > 0" class="citations">
            <div class="citations-title">参考资料</div>
            <article v-for="(cite, j) in msg.citations" :key="j" class="citation-item">
              <div class="citation-head">
                <strong>{{ citationTitle(cite, j) }}</strong>
                <span v-if="citationMeta(cite)">{{ citationMeta(cite) }}</span>
              </div>
              <p v-if="citationContent(cite)">{{ citationContent(cite) }}</p>
              <small v-if="citationSource(cite)">{{ citationSource(cite) }}</small>
            </article>
          </div>
          <div v-if="msg.traceId" class="trace-id">Trace ID: {{ msg.traceId }}</div>
        </div>
      </main>

      <div v-if="suggestedQuestions.length > 0" class="suggested-questions">
        <p>{{ messages.length === 0 ? '试试这些问题' : '你还可以继续问' }}</p>
        <div class="questions">
          <div
            v-for="(q, i) in suggestedQuestions"
            :key="i"
            class="question-chip"
          >
            <button class="question-btn" @click="useSuggestedQuestion(q)">
              {{ q }}
            </button>
            <button
              class="question-dismiss"
              type="button"
              title="不感兴趣"
              aria-label="不感兴趣"
              @click="dismissSuggestedQuestion(q)"
            >
              ×
            </button>
          </div>
        </div>
      </div>

      <footer class="input-area">
        <input
          v-model="message"
          placeholder="比如：最近一周总是晚睡，怎么调整作息更稳妥？"
          @keyup.enter="sendMessage"
          :disabled="loading"
        />
        <button @click="sendMessage" :disabled="loading || !message.trim()">
          {{ loading ? '生成中...' : '发送' }}
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.home-view {
  height: calc(100vh - 81px);
  min-height: 0;
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 24px;
  padding: 24px;
  overflow: hidden;
}

.sidebar {
  background: var(--surface-primary);
  border: 1px solid var(--border-soft);
  border-radius: 28px;
  box-shadow: var(--shadow-soft);
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 24px;
  border-bottom: 1px solid var(--border-soft);
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 18px;
}

.sidebar-brand img {
  width: 42px;
  height: 42px;
}

.sidebar-brand strong {
  display: block;
  font-size: 16px;
  color: var(--text-primary);
}

.sidebar-brand p {
  font-size: 12px;
  color: var(--text-secondary);
}

.trace-id {
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  opacity: 0.75;
}

.new-chat-btn {
  width: 100%;
  padding: 13px 16px;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, var(--brand-primary) 0%, #4096ff 100%);
  color: #fff;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  box-shadow: 0 14px 26px rgba(22, 119, 255, 0.24);
}

.new-chat-btn span {
  font-size: 18px;
  line-height: 1;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.session-empty {
  padding: 18px 14px;
  color: var(--text-secondary);
  font-size: 13px;
  text-align: center;
}

.session-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 13px;
  border-radius: 18px;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    transform 0.2s ease,
    box-shadow 0.2s ease;
  margin-bottom: 8px;
}

.session-item:hover {
  background: rgba(22, 119, 255, 0.06);
  transform: translateY(-1px);
}

.session-item.active {
  background: linear-gradient(180deg, rgba(22, 119, 255, 0.12), rgba(22, 119, 255, 0.05));
  box-shadow: inset 0 0 0 1px rgba(22, 119, 255, 0.16);
}

.session-icon {
  width: 38px;
  height: 38px;
  border-radius: 14px;
  background: var(--brand-primary-soft);
  color: var(--brand-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 700;
  flex-shrink: 0;
}

.session-info {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 4px;
}

.session-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.session-preview {
  font-size: 12px;
  line-height: 1.35;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-time {
  width: fit-content;
  max-width: 100%;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(22, 119, 255, 0.07);
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.conversation-panel {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.conversation-topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 6px 0;
}

.menu-btn {
  display: none;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  border: none;
  border-radius: 14px;
  background: rgba(22, 119, 255, 0.08);
  cursor: pointer;
}

.menu-btn span {
  display: block;
  width: 18px;
  height: 2px;
  border-radius: 999px;
  background: var(--brand-primary);
}

.topbar-copy h1 {
  font-size: 28px;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.topbar-copy p {
  font-size: 14px;
  color: var(--text-secondary);
}

.chat-area {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  gap: 28px;
  padding: 20px 4px 8px;
}

.empty-hero {
  display: grid;
  grid-template-columns: 84px minmax(0, 1fr);
  gap: 20px;
  padding: 28px;
  border-radius: 28px;
  background: linear-gradient(135deg, rgba(22, 119, 255, 0.12), rgba(255, 255, 255, 0.84));
  border: 1px solid rgba(22, 119, 255, 0.14);
  box-shadow: var(--shadow-card);
}

.hero-logo {
  width: 84px;
  height: 84px;
}

.hero-badge {
  display: inline-flex;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(22, 119, 255, 0.1);
  color: var(--brand-primary);
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 12px;
}

.empty-hero h2 {
  font-size: 32px;
  line-height: 1.25;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.empty-hero p {
  font-size: 15px;
  color: var(--text-secondary);
  max-width: 760px;
}

.capability-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.capability-card {
  padding: 22px;
  border-radius: 24px;
  background: var(--surface-primary);
  border: 1px solid var(--border-soft);
  box-shadow: var(--shadow-soft);
}

.capability-icon {
  width: 40px;
  height: 40px;
  border-radius: 14px;
  background: var(--brand-primary-soft);
  color: var(--brand-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 14px;
}

.capability-card h3 {
  font-size: 18px;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.capability-card p {
  font-size: 13px;
  color: var(--text-secondary);
}

.message {
  margin-bottom: 18px;
  display: flex;
  flex-direction: column;
}

.message.user {
  align-items: flex-end;
}

.message.assistant {
  align-items: flex-start;
}

.bubble {
  max-width: min(78%, 760px);
  padding: 15px 18px;
  border-radius: 22px;
  background: var(--surface-primary);
  color: var(--text-primary);
  border: 1px solid rgba(22, 119, 255, 0.1);
  box-shadow: var(--shadow-soft);
  white-space: pre-wrap;
  line-height: 1.7;
}

.message.assistant .bubble {
  white-space: normal;
}

.message.user .bubble {
  background: linear-gradient(135deg, var(--brand-primary) 0%, #4096ff 100%);
  color: #fff;
  border-color: transparent;
}

.citations {
  margin-top: 10px;
  width: min(78%, 760px);
  padding: 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(22, 119, 255, 0.12);
  color: var(--text-secondary);
  font-size: 12px;
}

.citations-title {
  margin-bottom: 8px;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 700;
}

.citation-item {
  padding: 10px 0;
  border-top: 1px solid rgba(22, 119, 255, 0.08);
}

.citation-item:first-of-type {
  border-top: 0;
  padding-top: 0;
}

.citation-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.citation-head strong {
  min-width: 0;
  color: var(--text-primary);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.citation-head span {
  flex-shrink: 0;
  color: var(--text-tertiary);
}

.citation-item p {
  margin: 0 0 6px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.citation-item small {
  display: block;
  color: var(--text-tertiary);
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.typing-indicator {
  display: inline-flex;
  gap: 4px;
  margin-left: 8px;
  vertical-align: middle;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.5;
  animation: pulse 1s infinite ease-in-out;
}

.dot:nth-child(2) {
  animation-delay: 0.15s;
}

.dot:nth-child(3) {
  animation-delay: 0.3s;
}

.suggested-questions {
  padding: 0 4px;
}

.suggested-questions p {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.questions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.question-chip {
  display: inline-flex;
  align-items: stretch;
  border: 1px solid rgba(22, 119, 255, 0.12);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.76);
  overflow: hidden;
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    background-color 0.2s ease;
}

.question-chip:hover {
  transform: translateY(-1px);
  border-color: rgba(22, 119, 255, 0.28);
  background: rgba(230, 244, 255, 0.88);
}

.question-btn,
.question-dismiss {
  border: none;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
}

.question-btn {
  padding: 11px 8px 11px 16px;
  max-width: min(420px, 72vw);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.question-dismiss {
  width: 34px;
  padding: 0;
  color: var(--text-tertiary);
  font-size: 17px;
  line-height: 1;
}

.question-dismiss:hover {
  color: var(--brand-primary);
  background: rgba(22, 119, 255, 0.08);
}

.markdown-body {
  white-space: normal;
  word-break: break-word;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 16px 0 8px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--text-primary);
}

.markdown-body :deep(h1) { font-size: 1.4em; }
.markdown-body :deep(h2) { font-size: 1.25em; }
.markdown-body :deep(h3) { font-size: 1.1em; }

.markdown-body :deep(p) {
  margin: 0 0 10px;
  line-height: 1.7;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 8px 0;
  padding-left: 22px;
}

.markdown-body :deep(li) {
  margin: 4px 0;
  line-height: 1.7;
}

.markdown-body :deep(code) {
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(22, 119, 255, 0.08);
  font-size: 0.9em;
  font-family: 'SF Mono', 'Fira Code', Consolas, monospace;
}

.markdown-body :deep(pre) {
  margin: 10px 0;
  padding: 14px 16px;
  border-radius: 14px;
  background: #1e1e2e;
  color: #cdd6f4;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.6;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: none;
  color: inherit;
  font-size: inherit;
}

.markdown-body :deep(blockquote) {
  margin: 10px 0;
  padding: 8px 14px;
  border-left: 3px solid var(--brand-primary);
  background: rgba(22, 119, 255, 0.05);
  border-radius: 0 10px 10px 0;
  color: var(--text-secondary);
}

.markdown-body :deep(blockquote p) {
  margin: 0;
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 8px 12px;
  border: 1px solid rgba(22, 119, 255, 0.12);
  text-align: left;
}

.markdown-body :deep(th) {
  background: rgba(22, 119, 255, 0.06);
  font-weight: 600;
}

.markdown-body :deep(strong) {
  font-weight: 600;
  color: var(--text-primary);
}

.markdown-body :deep(a) {
  color: var(--brand-primary);
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.markdown-body :deep(hr) {
  margin: 14px 0;
  border: none;
  border-top: 1px solid rgba(22, 119, 255, 0.1);
}

.input-area {
  display: flex;
  gap: 12px;
  padding: 18px;
  background: var(--surface-primary);
  border: 1px solid var(--border-soft);
  border-radius: 26px;
  box-shadow: var(--shadow-soft);
}

.input-area input {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  color: var(--text-primary);
  outline: none;
}

.input-area input::placeholder {
  color: var(--text-tertiary);
}

.input-area button {
  padding: 12px 22px;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, var(--brand-primary) 0%, #4096ff 100%);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
}

.input-area button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.sidebar-overlay {
  display: none;
}

@keyframes pulse {
  0%,
  80%,
  100% {
    transform: scale(0.85);
    opacity: 0.4;
  }

  40% {
    transform: scale(1);
    opacity: 0.9;
  }
}

@media (max-width: 1100px) {
  .capability-grid {
    grid-template-columns: 1fr;
  }

  .empty-hero h2 {
    font-size: 26px;
  }
}

@media (max-width: 960px) {
  .home-view {
    grid-template-columns: 1fr;
    height: calc(100vh - 137px);
    padding: 16px;
  }

  .sidebar {
    position: fixed;
    left: 16px;
    top: 112px;
    bottom: 16px;
    width: min(320px, calc(100vw - 32px));
    transform: translateX(calc(-100% - 20px));
    transition: transform 0.25s ease;
    z-index: 40;
  }

  .sidebar.open {
    transform: translateX(0);
  }

  .sidebar-overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(9, 30, 66, 0.32);
    z-index: 35;
  }

  .menu-btn {
    display: inline-flex;
  }
}

@media (max-width: 720px) {
  .conversation-topbar {
    align-items: flex-start;
  }

  .empty-hero {
    grid-template-columns: 1fr;
    padding: 22px;
  }

  .hero-logo {
    width: 68px;
    height: 68px;
  }

  .empty-hero h2 {
    font-size: 22px;
  }

  .bubble {
    max-width: 100%;
  }

  .input-area {
    flex-direction: column;
  }

  .input-area button {
    width: 100%;
  }
}
</style>
