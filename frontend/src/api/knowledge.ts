import { authHeaders, ensureAuthorizedResponse } from './auth'
import { apiUrl } from './client'

export interface KnowledgeFileImportPayload {
  file: File
  category?: string
  topic?: string
  chunkSize?: number
  chunkOverlap?: number
  dryRun?: boolean
}

export interface KnowledgeFileImportResponse {
  status: string
  filename: string
  title: string
  source_type: string
  category?: string | null
  topic?: string | null
  source_document_count: number
  chunk_count: number
  imported_count: number
  index_name: string
  dry_run: boolean
  preview_ids: string[]
}

function formatApiError(error: any, fallback: string) {
  const detail = error?.detail
  if (typeof detail === 'string') {
    return detail
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || '参数不合法').join('；')
  }
  return fallback
}

export async function importKnowledgeFile(payload: KnowledgeFileImportPayload) {
  const formData = new FormData()
  formData.append('file', payload.file)
  formData.append('category', payload.category || 'health')
  if (payload.topic) {
    formData.append('topic', payload.topic)
  }
  formData.append('chunk_size', String(payload.chunkSize || 700))
  formData.append('chunk_overlap', String(payload.chunkOverlap || 80))
  formData.append('dry_run', String(Boolean(payload.dryRun)))

  const response = await fetch(apiUrl('/api/v1/knowledge/import-file'), {
    method: 'POST',
    headers: {
      ...authHeaders(),
      Accept: 'application/json',
    },
    body: formData,
  })

  if (!ensureAuthorizedResponse(response)) {
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(formatApiError(error, '知识文件入库失败'))
  }

  return (await response.json()) as KnowledgeFileImportResponse
}

export const importKnowledgePdf = importKnowledgeFile
export type KnowledgePdfImportPayload = KnowledgeFileImportPayload
export type KnowledgePdfImportResponse = KnowledgeFileImportResponse
