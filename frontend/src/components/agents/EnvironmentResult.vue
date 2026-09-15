<script setup lang="ts">
import { computed } from 'vue'
import { ElCard, ElTag, ElProgress, ElDivider, ElAlert } from 'element-plus'
import { Sunny, Warning } from '@element-plus/icons-vue'
import type { EnvironmentResponse } from '@/api/agents'

interface Props {
  result: EnvironmentResponse['data']
}

const props = defineProps<Props>()
const airQuality = computed(() => props.result.air_quality)
const weather = computed(() => props.result.weather)
const specialWarnings = computed(() => props.result.special_warnings ?? [])
const riskStyle = computed(() => getRiskLevelStyle(props.result.risk_level))

// 获取AQI等级信息
const getAQILevel = (aqi: number) => {
  if (aqi <= 50) return { level: '优', color: '#52c41a', description: '空气质量令人满意' }
  if (aqi <= 100) return { level: '良', color: '#52c41a', description: '空气质量可接受' }
  if (aqi <= 150) return { level: '轻度污染', color: '#faad14', description: '敏感人群症状轻度加剧' }
  if (aqi <= 200) return { level: '中度污染', color: '#fa8c16', description: '进一步加剧易感人群症状' }
  if (aqi <= 300) return { level: '重度污染', color: '#f5222d', description: '心脏病和肺病患者症状显著加剧' }
  return { level: '严重污染', color: '#820014', description: '健康人群运动耐受力降低' }
}

// 获取风险等级样式
const getRiskLevelStyle = (level: string) => {
  const styles: Record<string, { color: string; bg: string; icon: string }> = {
    'low': {
      color: '#67c23a',
      bg: '#f0f9eb',
      icon: '✓'
    },
    'medium': {
      color: '#e6a23c',
      bg: '#fdf6ec',
      icon: '!'
    },
    'high': {
      color: '#f56c6c',
      bg: '#fef0f0',
      icon: '⚠'
    },
    'severe': {
      color: '#ff4d4f',
      bg: '#fff2f0',
      icon: '⛔'
    }
  }
  const fallback = { color: '#67c23a', bg: '#f0f9eb', icon: '✓' }
  return styles[level] ?? fallback
}

// 获取天气图标
const getWeatherIcon = (description: string) => {
  if (description.includes('晴')) return '☀️'
  if (description.includes('云') || description.includes('阴')) return '☁️'
  if (description.includes('雨')) return '🌧️'
  if (description.includes('雪')) return '❄️'
  if (description.includes('雾') || description.includes('霾')) return '🌫️'
  return '🌤️'
}

// 计算PM2.5进度条颜色
const getPM25ProgressColor = (pm25: number) => {
  if (pm25 <= 35) return '#67c23a'
  if (pm25 <= 75) return '#e6a23c'
  if (pm25 <= 115) return '#f56c6c'
  return '#ff4d4f'
}
</script>

<template>
  <div class="environment-result">
    <!-- 风险等级卡片 -->
    <ElCard
      class="risk-card"
      :style="{ borderColor: riskStyle.color }"
      shadow="hover"
    >
      <div class="risk-content" :style="{ background: riskStyle.bg }">
        <div class="risk-icon" :style="{ color: riskStyle.color }">
          {{ riskStyle.icon }}
        </div>
        <div class="risk-info">
          <div class="risk-title" :style="{ color: riskStyle.color }">
            健康风险等级：{{ result.risk_level === 'low' ? '低' : result.risk_level === 'medium' ? '中' : result.risk_level === 'high' ? '高' : '极高' }}
          </div>
          <div class="risk-desc">{{ result.outdoor_suitable ? '✓ 适合户外活动' : '✗ 建议减少户外活动' }}</div>
          <div class="exercise-advice">💪 {{ result.exercise_recommendation }}</div>
        </div>
      </div>
    </ElCard>

    <!-- 空气质量卡片 -->
    <ElCard v-if="airQuality" class="air-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span class="card-emoji">🌬️</span>
          <span>空气质量</span>
          <ElTag :color="getAQILevel(airQuality.aqi).color" effect="dark" size="small">
            {{ airQuality.aqi }} - {{ getAQILevel(airQuality.aqi).level }}
          </ElTag>
        </div>
      </template>

      <div class="air-content">
        <div class="aqi-display">
          <div class="aqi-value" :style="{ color: getAQILevel(airQuality.aqi).color }">
            {{ airQuality.aqi }}
          </div>
          <div class="aqi-level">{{ getAQILevel(airQuality.aqi).level }}</div>
          <div class="aqi-desc">{{ getAQILevel(airQuality.aqi).description }}</div>
        </div>

        <ElDivider />

        <div class="pollutants-grid">
          <div class="pollutant-item">
            <div class="pollutant-name">PM2.5</div>
            <div class="pollutant-value">{{ airQuality.pm25 }}</div>
            <ElProgress
              :percentage="Math.min(airQuality.pm25, 100)"
              :color="getPM25ProgressColor(airQuality.pm25)"
              :show-text="false"
              :stroke-width="6"
            />
          </div>
          <div class="pollutant-item">
            <div class="pollutant-name">PM10</div>
            <div class="pollutant-value">{{ airQuality.pm10 || '-' }}</div>
            <ElProgress
              :percentage="Math.min((airQuality.pm10 || 0) / 2, 100)"
              color="#909399"
              :show-text="false"
              :stroke-width="6"
            />
          </div>
        </div>
      </div>
    </ElCard>

    <!-- 天气信息卡片 -->
    <ElCard v-if="weather" class="weather-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <ElIcon><Sunny /></ElIcon>
          <span>天气信息</span>
        </div>
      </template>

      <div class="weather-content">
        <div class="weather-main">
          <div class="weather-icon">{{ getWeatherIcon(weather.description) }}</div>
          <div class="weather-temp">{{ weather.temp }}°C</div>
          <div class="weather-desc">{{ weather.description }}</div>
        </div>

        <ElDivider />

        <div class="weather-details">
          <div class="detail-item">
            <div class="detail-label">体感温度</div>
            <div class="detail-value">{{ weather.feels_like }}°C</div>
          </div>
          <div class="detail-item">
            <div class="detail-label">湿度</div>
            <div class="detail-value">{{ weather.humidity }}%</div>
          </div>
          <div v-if="weather.wind_speed" class="detail-item">
            <div class="detail-label">风速</div>
            <div class="detail-value">{{ weather.wind_speed }} m/s</div>
          </div>
        </div>
      </div>
    </ElCard>

    <!-- 特殊提醒 -->
    <ElCard v-if="specialWarnings.length > 0" class="warnings-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <ElIcon><Warning /></ElIcon>
          <span>特殊提醒</span>
        </div>
      </template>

      <div class="special-warnings">
        <ElAlert
          v-for="(warning, index) in specialWarnings"
          :key="index"
          :title="warning"
          type="warning"
          :closable="false"
          show-icon
          class="warning-alert"
        />
      </div>
    </ElCard>
  </div>
</template>

<style scoped lang="scss">
.environment-result {
  display: flex;
  flex-direction: column;
  gap: 16px;

  :deep(.el-card) {
    border-radius: 12px;
  }
}

// 风险等级卡片
.risk-card {
  :deep(.el-card__body) {
    padding: 0;
  }

  .risk-content {
    display: flex;
    align-items: center;
    gap: 24px;
    padding: 24px;
    border-radius: 12px;
  }

  .risk-icon {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    background: #fff;
  }

  .risk-info {
    flex: 1;

    .risk-title {
      font-size: 20px;
      font-weight: 600;
      margin-bottom: 8px;
    }

    .risk-desc {
      font-size: 14px;
      color: #606266;
      margin-bottom: 4px;
    }

    .exercise-advice {
      font-size: 13px;
      color: #409eff;
    }
  }
}

// 空气卡片
.air-card {
  .card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
  }

  .air-content {
    .aqi-display {
      text-align: center;
      padding: 24px;

      .aqi-value {
        font-size: 56px;
        font-weight: 700;
        line-height: 1;
        margin-bottom: 8px;
      }

      .aqi-level {
        font-size: 20px;
        font-weight: 600;
        margin-bottom: 8px;
      }

      .aqi-desc {
        font-size: 14px;
        color: #909399;
      }
    }

    .pollutants-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      padding: 16px;

      .pollutant-item {
        text-align: center;
        padding: 16px;
        background: #f5f7fa;
        border-radius: 8px;

        .pollutant-name {
          font-size: 12px;
          color: #909399;
          margin-bottom: 4px;
        }

        .pollutant-value {
          font-size: 24px;
          font-weight: 600;
          color: #303133;
          margin-bottom: 8px;
        }
      }
    }
  }
}

// 天气卡片
.weather-card {
  .card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
  }

  .weather-content {
    .weather-main {
      text-align: center;
      padding: 24px;

      .weather-icon {
        font-size: 64px;
        margin-bottom: 8px;
      }

      .weather-temp {
        font-size: 48px;
        font-weight: 700;
        color: #303133;
        line-height: 1;
        margin-bottom: 4px;
      }

      .weather-desc {
        font-size: 16px;
        color: #606266;
      }
    }

    .weather-details {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
      padding: 16px;

      .detail-item {
        text-align: center;
        padding: 12px;
        background: #f5f7fa;
        border-radius: 8px;

        .detail-label {
          font-size: 12px;
          color: #909399;
          margin-bottom: 4px;
        }

        .detail-value {
          font-size: 16px;
          font-weight: 600;
          color: #303133;
        }
      }
    }
  }
}

// 警告卡片
.warnings-card {
  .card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    color: #e6a23c;
  }

  .special-warnings {
    display: flex;
    flex-direction: column;
    gap: 8px;

    .warning-alert {
      margin: 0;
    }
  }
}

// 响应式
@media (max-width: 768px) {
  .risk-card {
    .risk-content {
      flex-direction: column;
      gap: 16px;
    }

    .risk-info {
      text-align: center;
    }
  }

  .air-card {
    .pollutants-grid {
      grid-template-columns: 1fr;
    }
  }

  .weather-card {
    .weather-details {
      grid-template-columns: 1fr;
    }
  }
}
</style>
