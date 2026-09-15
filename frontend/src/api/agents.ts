/**
 * Agent专用API模块
 * 营养分析、环境查询、运动计划等Agent接口
 */

import { authHeaders, ensureAuthorizedResponse } from './auth'
import { apiUrl } from './client'

// ==================== 类型定义 ====================

/**
 * 营养分析请求
 */
export interface NutritionRequest {
  description: string
  image_url?: string
  user_id?: string
}

/**
 * 营养成分
 */
export interface NutritionInfo {
  calories: number
  protein: number
  fat: number
  carbs: number
  fiber?: number
  sodium?: number
}

/**
 * 食物项
 */
export interface FoodItem {
  name: string
  grams: number
  calories: number
  protein: number
  fat: number
  carbs: number
}

/**
 * 营养分析响应
 */
export interface NutritionResponse {
  trace_id?: string
  prompt_security?: {
    risk_level: string
    is_suspicious: boolean
    categories: string[]
    warning?: string | null
  }
  agent: 'nutrition'
  status: 'success' | 'error'
  data: {
    foods: FoodItem[]
    total: NutritionInfo
    advice: string
    warnings: string[]
    score: number
    ocr_text?: string
  }
}

/**
 * 环境查询请求
 */
export interface EnvironmentRequest {
  location: string
  query_type?: 'air' | 'weather' | 'traffic' | 'all'
}

/**
 * 空气质量数据
 */
export interface AirQualityData {
  aqi: number
  level: string
  pm25: number
  pm10?: number
  main_pollutant?: string
}

/**
 * 天气数据
 */
export interface WeatherData {
  temp: number
  feels_like: number
  humidity: number
  description: string
  wind_speed?: number
}

/**
 * 环境查询响应
 */
export interface EnvironmentResponse {
  trace_id?: string
  prompt_security?: {
    risk_level: string
    is_suspicious: boolean
    categories: string[]
    warning?: string | null
  }
  agent: 'environment'
  status: 'success' | 'error'
  data: {
    air_quality?: AirQualityData
    weather?: WeatherData
    risk_level: 'low' | 'medium' | 'high' | 'severe'
    outdoor_suitable: boolean
    exercise_recommendation: string
    special_warnings: string[]
  }
}

/**
 * 运动计划请求
 */
export interface ExerciseRequest {
  goal: string
  fitness_level?: 'beginner' | 'intermediate' | 'advanced'
  time_minutes?: number
  user_id?: string
}

/**
 * 运动项
 */
export interface ExerciseItem {
  name: string
  type: string
  duration_min: number
  intensity: 'low' | 'medium' | 'high'
  calories_per_hour?: number
  benefits: string
  precautions?: string
}

/**
 * 运动计划响应
 */
export interface ExerciseResponse {
  trace_id?: string
  prompt_security?: {
    risk_level: string
    is_suspicious: boolean
    categories: string[]
    warning?: string | null
  }
  agent: 'exercise'
  status: 'success' | 'error'
  data: {
    type: 'recommend' | 'plan' | 'analyze'
    fitness_level: string
    exercises: ExerciseItem[]
    env_adjustments?: string[]
    safety_constraints?: string[]
    advice?: string
  }
}

/**
 * Agent列表响应
 */
export interface AgentListResponse {
  agents: Array<{
    name: string
    description: string
    icon: string
  }>
}

// ==================== API函数 ====================

/**
 * 获取Agent列表
 */
export async function getAgents(): Promise<AgentListResponse> {
  const response = await fetch(apiUrl('/api/v1/agents'), {
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
    throw new Error('获取Agent列表失败')
  }

  return response.json()
}

/**
 * 营养分析
 * @param params 营养分析请求参数
 */
export async function analyzeNutrition(params: NutritionRequest): Promise<NutritionResponse> {
  const response = await fetch(apiUrl('/api/v1/agents/nutrition/analyze'), {
    method: 'POST',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(params),
  })

  if (!ensureAuthorizedResponse(response)) {
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '营养分析失败')
  }

  return response.json()
}

/**
 * 环境查询
 * @param params 环境查询请求参数
 */
export async function queryEnvironment(params: EnvironmentRequest): Promise<EnvironmentResponse> {
  const response = await fetch(apiUrl('/api/v1/agents/environment/query'), {
    method: 'POST',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(params),
  })

  if (!ensureAuthorizedResponse(response)) {
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '环境查询失败')
  }

  return response.json()
}

/**
 * 生成运动计划
 * @param params 运动计划请求参数
 */
export async function generateExercisePlan(params: ExerciseRequest): Promise<ExerciseResponse> {
  const response = await fetch(apiUrl('/api/v1/agents/exercise/plan'), {
    method: 'POST',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify(params),
  })

  if (!ensureAuthorizedResponse(response)) {
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '生成运动计划失败')
  }

  return response.json()
}

// Default export
export default {
  getAgents,
  analyzeNutrition,
  queryEnvironment,
  generateExercisePlan,
}
