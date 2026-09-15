/**
 * 健康档案API模块
 */

import { authHeaders, ensureAuthorizedResponse } from './auth'
import { apiUrl } from './client'

/**
 * 获取用户健康档案
 */
export async function getHealthProfile(type?: 'steps' | 'sleep' | 'heart_rate' | 'all', startDate?: string, endDate?: string) {
  const params = new URLSearchParams()
  if (type) params.append('type', type)
  if (startDate) params.append('startDate', startDate)
  if (endDate) params.append('endDate', endDate)

  const response = await fetch(apiUrl(`/api/v1/health/profile?${params}`), {
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
    throw new Error('获取健康档案失败')
  }

  return response.json()
}

/**
 * 导入健康数据
 */
export async function importHealthData(format: 'csv' | 'json', dataType: 'steps' | 'sleep' | 'heart_rate' | 'all', file: File) {
  const formData = new FormData()
  formData.append('format', format)
  formData.append('data_type', dataType)
  formData.append('dataType', dataType)
  formData.append('file', file)

  const response = await fetch(apiUrl('/api/v1/health/import'), {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  })

  if (!ensureAuthorizedResponse(response)) {
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '导入失败')
  }

  return response.json()
}

/**
 * 删除健康数据
 */
export async function deleteHealthRecords(recordIds?: string[], dateRange?: { startDate: string; endDate: string }) {
  const body: any = {}
  if (recordIds) body.recordIds = recordIds
  if (dateRange) body.dateRange = dateRange

  const response = await fetch(apiUrl('/api/v1/health/records'), {
    method: 'DELETE',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  if (!ensureAuthorizedResponse(response)) {
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    throw new Error('删除失败')
  }

  return response.json()
}

/**
 * 获取健康数据统计
 */
export function getHealthStats(data: any[], type?: 'steps' | 'sleep' | 'heart_rate') {
  if (!data || data.length === 0) {
    return null
  }

  const fieldMap: Record<string, string> = { steps: 'steps', sleep: 'duration', heart_rate: 'resting' }
  const values = data
    .map(d => {
      if (type && fieldMap[type]) {
        return d[fieldMap[type]]
      }
      return d.value || d.steps || d.duration || d.resting
    })
    .filter(v => typeof v === 'number')

  if (values.length === 0) {
    return null
  }

  const sum = values.reduce((a, b) => a + b, 0)
  const avg = sum / values.length
  const max = Math.max(...values)
  const min = Math.min(...values)

  return {
    total: sum,
    average: Math.round(avg * 10) / 10,
    max,
    min,
    count: values.length,
  }
}

/**
 * 生成模拟健康数据（用于开发测试）
 */
export function generateMockHealthData(type: 'steps' | 'sleep' | 'heart_rate', days: number = 30) {
  const data: Array<Record<string, number | string>> = []
  const now = new Date()

  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    const dateStr = date.toISOString().split('T')[0] ?? ''

    if (type === 'steps') {
      data.push({
        date: dateStr,
        steps: Math.floor(Math.random() * 8000) + 4000,
        distance: Math.floor(Math.random() * 5) + 2,
        calories: Math.floor(Math.random() * 400) + 200,
      })
    } else if (type === 'sleep') {
      data.push({
        date: dateStr,
        duration: Math.random() * 3 + 5,
        deepSleep: Math.random() * 2 + 1,
        lightSleep: Math.random() * 2 + 2,
        quality: ['excellent', 'good', 'fair', 'poor'][Math.floor(Math.random() * 4)] ?? 'good',
      })
    } else if (type === 'heart_rate') {
      data.push({
        date: dateStr,
        resting: Math.floor(Math.random() * 20) + 60,
        max: Math.floor(Math.random() * 40) + 140,
        avg: Math.floor(Math.random() * 30) + 70,
      })
    }
  }

  return data
}

export default {
  getHealthProfile,
  importHealthData,
  deleteHealthRecords,
  getHealthStats,
  generateMockHealthData,
}
