<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useHealthStore } from '@/stores/health'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Download, TrendCharts, DataLine, FirstAidKit } from '@element-plus/icons-vue'
import StepsChart from '@/components/charts/StepsChart.vue'
import SleepChart from '@/components/charts/SleepChart.vue'
import HeartRateChart from '@/components/charts/HeartRateChart.vue'

const healthStore = useHealthStore()
const { stepsData, sleepData, heartRateData } = storeToRefs(healthStore)

const activeTab = ref('overview')

onMounted(async () => {
  await healthStore.loadHealthData()
})

const stats = computed(() => ({
  steps: healthStore.stepsStats,
  sleep: healthStore.sleepStats,
  heartRate: healthStore.heartRateStats,
}))

const recentData = computed(() => ({
  steps: healthStore.recentSteps,
  sleep: healthStore.recentSleep,
  heartRate: healthStore.recentHeartRate,
}))

async function refreshData() {
  await healthStore.loadHealthData()
  ElMessage.success('数据已刷新')
}

function exportData() {
  const data = {
    steps: healthStore.stepsData,
    sleep: healthStore.sleepData,
    heartRate: healthStore.heartRateData,
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `health-data-${new Date().toISOString().split('T')[0]}.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('数据导出成功')
}

async function clearData() {
  try {
    await ElMessageBox.confirm(
      '确定要清除所有健康数据吗？此操作不可恢复。',
      '警告',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    healthStore.clearData()
    ElMessage.success('数据已清除')
  } catch {
    return
  }
}

function getDataStatusLabel(type: 'steps' | 'sleep' | 'heart_rate') {
  const dataMap = {
    steps: healthStore.stepsData,
    sleep: healthStore.sleepData,
    heart_rate: healthStore.heartRateData,
  }
  const count = dataMap[type].length
  if (count === 0) return { text: '无数据', type: 'info' as const }
  if (count < 7) return { text: '数据较少', type: 'warning' as const }
  return { text: `${count}天数据`, type: 'success' as const }
}

function getQualityType(quality?: string) {
  const typeMap: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
    excellent: 'success',
    good: 'success',
    fair: 'warning',
    poor: 'danger',
  }
  return typeMap[quality || ''] || 'info'
}
</script>

<template>
  <div class="health-view">
    <div class="page-header">
      <div class="header-left">
        <div class="header-icon">
          <el-icon :size="26"><FirstAidKit /></el-icon>
        </div>
        <div>
          <h1>健康档案</h1>
          <p class="subtitle">集中查看你的步数、睡眠和心率变化，形成更稳定的日常健康节奏。</p>
        </div>
      </div>

      <div class="header-actions">
        <el-button type="primary" @click="$router.push('/import')">
          <el-icon><DataLine /></el-icon>
          导入数据
        </el-button>
        <el-button @click="refreshData">
          <el-icon><TrendCharts /></el-icon>
          刷新
        </el-button>
        <el-button @click="exportData">
          <el-icon><Download /></el-icon>
          导出
        </el-button>
        <el-button type="danger" plain @click="clearData">
          <el-icon><Delete /></el-icon>
          清除
        </el-button>
      </div>
    </div>

    <div class="stats-overview">
      <el-card class="stat-card" :class="{ 'no-data': !stats.steps }">
        <div class="stat-header">
          <div class="stat-icon steps">步</div>
          <el-tag :type="getDataStatusLabel('steps').type" size="small">
            {{ getDataStatusLabel('steps').text }}
          </el-tag>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.steps?.average?.toLocaleString() || '-' }}</div>
          <div class="stat-label">平均步数 / 天</div>
        </div>
        <div class="stat-footer">
          <span>总计 {{ stats.steps?.total?.toLocaleString() || '-' }} 步</span>
          <span>最高 {{ stats.steps?.max?.toLocaleString() || '-' }} 步</span>
        </div>
      </el-card>

      <el-card class="stat-card" :class="{ 'no-data': !stats.sleep }">
        <div class="stat-header">
          <div class="stat-icon sleep">眠</div>
          <el-tag :type="getDataStatusLabel('sleep').type" size="small">
            {{ getDataStatusLabel('sleep').text }}
          </el-tag>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.sleep?.average?.toFixed(1) || '-' }}</div>
          <div class="stat-label">平均睡眠 / 天</div>
        </div>
        <div class="stat-footer">
          <span>记录 {{ stats.sleep?.count || '-' }} 天</span>
          <span>最长 {{ stats.sleep?.max?.toFixed(1) || '-' }} 小时</span>
        </div>
      </el-card>

      <el-card class="stat-card" :class="{ 'no-data': !stats.heartRate }">
        <div class="stat-header">
          <div class="stat-icon heart">心</div>
          <el-tag :type="getDataStatusLabel('heart_rate').type" size="small">
            {{ getDataStatusLabel('heart_rate').text }}
          </el-tag>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ stats.heartRate?.average?.toFixed(0) || '-' }}</div>
          <div class="stat-label">平均静息心率</div>
        </div>
        <div class="stat-footer">
          <span>记录 {{ stats.heartRate?.count || '-' }} 天</span>
          <span>范围 {{ stats.heartRate?.min || '-' }} - {{ stats.heartRate?.max || '-' }} bpm</span>
        </div>
      </el-card>
    </div>

    <el-tabs v-model="activeTab" class="health-tabs" type="border-card">
      <el-tab-pane label="数据概览" name="overview">
        <div class="tab-content">
          <el-empty v-if="!healthStore.hasData" description="暂无数据">
            <el-button type="primary" @click="$router.push('/import')">导入数据</el-button>
          </el-empty>

          <div v-else class="overview-charts">
            <p class="section-desc">最近 7 天关键健康指标概览</p>

            <div v-if="recentData.steps.length" class="chart-section">
              <div class="chart-card">
                <div class="chart-card-header">
                  <span class="chart-card-title">
                    <span class="chart-dot steps-dot"></span>步数趋势
                  </span>
                  <span class="chart-card-sub">{{ recentData.steps.length }} 天</span>
                </div>
                <StepsChart :data="recentData.steps" height="240px" />
              </div>
            </div>

            <div v-if="recentData.sleep.length" class="chart-section">
              <div class="chart-card">
                <div class="chart-card-header">
                  <span class="chart-card-title">
                    <span class="chart-dot sleep-dot"></span>睡眠趋势
                  </span>
                  <span class="chart-card-sub">{{ recentData.sleep.length }} 天</span>
                </div>
                <SleepChart :data="recentData.sleep" height="240px" />
              </div>
            </div>

            <div v-if="recentData.heartRate.length" class="chart-section">
              <div class="chart-card">
                <div class="chart-card-header">
                  <span class="chart-card-title">
                    <span class="chart-dot heart-dot"></span>心率趋势
                  </span>
                  <span class="chart-card-sub">{{ recentData.heartRate.length }} 天</span>
                </div>
                <HeartRateChart :data="recentData.heartRate" height="240px" />
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="步数分析" name="steps">
        <div class="tab-content">
          <el-empty v-if="!stepsData.length" description="暂无步数数据">
            <el-button type="primary" @click="$router.push('/import')">导入步数数据</el-button>
          </el-empty>

          <div v-else>
            <p class="section-desc">共 {{ stepsData.length }} 天步数记录</p>
            <div class="chart-card" style="margin-bottom: 20px">
              <StepsChart :data="stepsData" title="步数趋势" height="300px" />
            </div>
            <div class="data-list">
              <div v-for="(item, index) in stepsData.slice(-10).reverse()" :key="index" class="data-item">
                <span class="date">{{ item.date }}</span>
                <span class="value">{{ item.steps?.toLocaleString() || '-' }} 步</span>
                <span class="extra">{{ item.distance }} km | {{ item.calories }} kcal</span>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="睡眠分析" name="sleep">
        <div class="tab-content">
          <el-empty v-if="!sleepData.length" description="暂无睡眠数据">
            <el-button type="primary" @click="$router.push('/import')">导入睡眠数据</el-button>
          </el-empty>

          <div v-else>
            <p class="section-desc">共 {{ sleepData.length }} 天睡眠记录</p>
            <div class="chart-card" style="margin-bottom: 20px">
              <SleepChart :data="sleepData" title="睡眠趋势" height="300px" />
            </div>
            <div class="data-list">
              <div v-for="(item, index) in sleepData.slice(-10).reverse()" :key="index" class="data-item">
                <span class="date">{{ item.date }}</span>
                <span class="value">{{ item.duration?.toFixed(1) || '-' }} 小时</span>
                <el-tag :type="getQualityType(item.quality)" size="small">{{ item.quality }}</el-tag>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="心率分析" name="heartrate">
        <div class="tab-content">
          <el-empty v-if="!heartRateData.length" description="暂无心率数据">
            <el-button type="primary" @click="$router.push('/import')">导入心率数据</el-button>
          </el-empty>

          <div v-else>
            <p class="section-desc">共 {{ heartRateData.length }} 天心率记录</p>
            <div class="chart-card" style="margin-bottom: 20px">
              <HeartRateChart :data="heartRateData" title="心率趋势" height="300px" />
            </div>
            <div class="data-list">
              <div v-for="(item, index) in heartRateData.slice(-10).reverse()" :key="index" class="data-item">
                <span class="date">{{ item.date }}</span>
                <span class="value">静息 {{ item.resting || '-' }} bpm</span>
                <span class="extra">最高 {{ item.max }} | 平均 {{ item.avg }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.health-view {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 24px;
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.header-icon {
  width: 52px;
  height: 52px;
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(22, 119, 255, 0.18), rgba(105, 177, 255, 0.22));
  color: var(--brand-primary);
  box-shadow: var(--shadow-soft);
}

.header-left h1 {
  font-size: 28px;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.subtitle {
  max-width: 680px;
  color: var(--text-secondary);
  font-size: 14px;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.stats-overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 18px;
  margin-bottom: 24px;
}

.stat-card {
  border-radius: 24px;
  transition:
    transform 0.2s ease,
    box-shadow 0.2s ease;
  background: var(--surface-primary);
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-card);
}

.stat-card.no-data {
  opacity: 0.72;
}

.stat-card :deep(.el-card__body) {
  padding: 22px;
}

.stat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.stat-icon {
  width: 46px;
  height: 46px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 16px;
  font-weight: 700;
}

.stat-icon.steps {
  background: linear-gradient(135deg, #1677ff 0%, #69b1ff 100%);
}

.stat-icon.sleep {
  background: linear-gradient(135deg, #36cfc9 0%, #73d13d 100%);
}

.stat-icon.heart {
  background: linear-gradient(135deg, #ff7875 0%, #ff9c6e 100%);
}

.stat-body {
  margin-bottom: 16px;
}

.stat-value {
  font-size: 38px;
  line-height: 1.1;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-label {
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.stat-footer {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(22, 119, 255, 0.1);
  color: var(--text-secondary);
  font-size: 13px;
}

.health-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
}

.health-tabs :deep(.el-tabs__nav-wrap) {
  padding: 0 20px;
}

.health-tabs :deep(.el-tabs__item) {
  height: 52px;
  line-height: 52px;
  font-size: 14px;
}

.health-tabs :deep(.el-tabs__item.is-active) {
  color: var(--brand-primary);
}

.health-tabs :deep(.el-tabs__active-bar) {
  background: var(--brand-primary);
}

.tab-content {
  min-height: 420px;
  padding: 24px;
}

.section-desc {
  margin-bottom: 14px;
  color: var(--text-secondary);
  font-size: 14px;
}

/* Overview chart grid */
.overview-charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
  gap: 18px;
}

.chart-section {
  min-width: 0;
}

.chart-card {
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(22, 119, 255, 0.08);
  border-radius: 20px;
  padding: 20px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.chart-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-card);
}

.chart-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.chart-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.chart-card-sub {
  font-size: 12px;
  color: var(--text-secondary);
}

.chart-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.steps-dot {
  background: #1677ff;
}

.sleep-dot {
  background: #36cfc9;
}

.heart-dot {
  background: #ff7875;
}

.data-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.data-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(22, 119, 255, 0.08);
  transition:
    transform 0.2s ease,
    background-color 0.2s ease;
}

.data-item:hover {
  transform: translateY(-1px);
  background: rgba(230, 244, 255, 0.72);
}

.date {
  width: 110px;
  flex-shrink: 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.value {
  width: 150px;
  flex-shrink: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.extra {
  flex: 1;
  text-align: right;
  font-size: 13px;
  color: var(--text-secondary);
}

@media (max-width: 900px) {
  .health-view {
    padding: 16px;
  }

  .page-header {
    flex-direction: column;
  }

  .overview-charts {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .stat-footer,
  .data-item {
    flex-direction: column;
    align-items: flex-start;
  }

  .date,
  .value,
  .extra {
    width: auto;
    text-align: left;
  }

  .tab-content {
    padding: 18px;
  }

  .overview-charts {
    grid-template-columns: 1fr;
  }
}
</style>
