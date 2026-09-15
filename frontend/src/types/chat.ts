export interface ChatMessage {
  id: string
  type: 'user' | 'ai' | 'system'
  content: string
  timestamp: number
  citations?: Citation[]
  attachments?: Attachment[]
  isStreaming?: boolean
  traceId?: string
}

export interface Citation {
  source: string
  content: string
}

export interface Attachment {
  type: 'image'
  url: string
}

export interface ChatSession {
  id: string
  title: string
  lastMessage: string
  timestamp: number
  messageCount: number
}

export type Session = ChatSession

export interface SendMessageRequest {
  message: string
  sessionId?: string
  attachments?: File[]
}

export interface SendMessageResponse {
  reply: string
  trace_id?: string
  citations: Citation[]
  suggestedQuestions: string[]
  safetyFlag?: string
  intent?: string
}

export interface StreamMessageChunk {
  content?: string
  citations?: Citation[]
  suggestedQuestions?: string[]
  trace_id?: string
  done?: boolean
}
