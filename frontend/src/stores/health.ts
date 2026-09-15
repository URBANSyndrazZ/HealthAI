import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as healthApi from '@/api/health'

export interface HealthData {
  date: string
  steps?: number
  distance?: number
  calories?: number
  duration?: number
  deepSleep?: number
  lightSleep?: number
  quality?: string
  resting?: number
  max?: number
  avg?: number
}

export interface HealthStats {
  total: number
  average: number
  max: number
  min: number
  count: number
}

type HealthDataType = 'steps' | 'sleep' | 'heart_rate'
type ImportStatus = 'idle' | 'processing' | 'completed' | 'partial' | 'failed'

/** 将后端 snake_case 字段名归一化为前端 camelCase */
function normalizeRecord(raw: any): HealthData {
  return {
    date: raw.date || '',
    steps: raw.steps,
    distance: raw.distance,
    calories: raw.calories,
    duration: raw.duration,
    deepSleep: raw.deepSleep ?? raw.deep_sleep,
    lightSleep: raw.lightSleep ?? raw.light_sleep,
    quality: raw.quality,
    resting: raw.resting,
    max: raw.max,
    avg: raw.avg,
  }
}

function getMockData(type: HealthDataType, days = 30): HealthData[] {
  return healthApi.generateMockHealthData(type, days) as unknown as HealthData[]
}

export const useHealthStore = defineStore('health', () => {
  // State
  const stepsData = ref<HealthData[]>([])
  const sleepData = ref<HealthData[]>([])
  const heartRateData = ref<HealthData[]>([])
  const isLoading = ref(false)
  const importProgress = ref({
    status: 'idle' as ImportStatus,
    importedCount: 0,
    failedCount: 0,
    errors: [] as string[],
  })

  // Getters
  const hasData = computed(() => {
    return stepsData.value.length > 0 || sleepData.value.length > 0 || heartRateData.value.length > 0
  })

  const stepsStats = computed(() => healthApi.getHealthStats(stepsData.value, 'steps'))
  const sleepStats = computed(() => healthApi.getHealthStats(sleepData.value, 'sleep'))
  const heartRateStats = computed(() => healthApi.getHealthStats(heartRateData.value, 'heart_rate'))

  const recentSteps = computed(() => {
    return stepsData.value.slice(-7)
  })

  const recentSleep = computed(() => {
    return sleepData.value.slice(-7)
  })

  const recentHeartRate = computed(() => {
    return heartRateData.value.slice(-7)
  })

  // Actions
  async function loadHealthData(type?: 'steps' | 'sleep' | 'heart_rate' | 'all') {
    isLoading.value = true
    try {
      const endDate = new Date().toISOString().split('T')[0]
      const startDate = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]

      const response = await healthApi.getHealthProfile(type, startDate, endDate)

      if (response.records) {
        if (!type || type === 'all' || type === 'steps') {
          stepsData.value = (response.records.steps || []).map(normalizeRecord)
        }
        if (!type || type === 'all' || type === 'sleep') {
          sleepData.value = (response.records.sleep || []).map(normalizeRecord)
        }
        if (!type || type === 'all' || type === 'heart_rate') {
          heartRateData.value = (response.records.heart_rate || []).map(normalizeRecord)
        }
      }
    } catch (error) {
      console.error('Failed to load health data:', error)
      // 开发阶段使用模拟数据
      stepsData.value = getMockData('steps')
      sleepData.value = getMockData('sleep')
      heartRateData.value = getMockData('heart_rate')
    } finally {
      isLoading.value = false
    }
  }

  async function importData(format: 'csv' | 'json', dataType: 'steps' | 'sleep' | 'heart_rate' | 'all', file: File) {
    importProgress.value = {
      status: 'processing',
      importedCount: 0,
      failedCount: 0,
      errors: [],
    }

    try {
      const result = await healthApi.importHealthData(format, dataType, file)
      importProgress.value = {
        status: (result.status || 'completed') as ImportStatus,
        importedCount: result.imported_count ?? result.importedCount ?? 0,
        failedCount: result.failed_count ?? result.failedCount ?? 0,
        errors: result.errors || [],
      }

      // 导入成功后刷新数据
      await loadHealthData(dataType)

      return result
    } catch (error: any) {
      importProgress.value = {
        status: 'failed',
        importedCount: 0,
        failedCount: 0,
        errors: [error.message || '导入失败'],
      }
      throw error
    }
  }

  function clearData() {
    stepsData.value = []
    sleepData.value = []
    heartRateData.value = []
  }

  function resetImportProgress() {
    importProgress.value = {
      status: 'idle',
      importedCount: 0,
      failedCount: 0,
      errors: [],
    }
  }

  // 使用模拟数据（开发测试用）
  function loadMockData() {
    stepsData.value = getMockData('steps', 30)
    sleepData.value = getMockData('sleep', 30)
    heartRateData.value = getMockData('heart_rate', 30)
  }

  return {
    // State
    stepsData,
    sleepData,
    heartRateData,
    isLoading,
    importProgress,
    // Getters
    hasData,
    stepsStats,
    sleepStats,
    heartRateStats,
    recentSteps,
    recentSleep,
    recentHeartRate,
    // Actions
    loadHealthData,
    importData,
    clearData,
    resetImportProgress,
    loadMockData,
  }
})
