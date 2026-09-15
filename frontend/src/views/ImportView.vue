<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useHealthStore } from '@/stores/health'
import { ElMessage } from 'element-plus'
import { Upload, Download, DataLine, FirstAidKit } from '@element-plus/icons-vue'

const router = useRouter()
const healthStore = useHealthStore()

const dataType = ref<'steps' | 'sleep' | 'heart_rate'>('steps')
const fileFormat = ref<'csv' | 'json'>('json')
const fileList = ref<File[]>([])
const isImporting = ref(false)
const importResult = ref<{
  status: string
  importedCount: number
  failedCount: number
  errors: string[]
} | null>(null)

const canImport = computed(() => fileList.value.length > 0 && !isImporting.value)

function handleFileChange(uploadFile: { raw?: File }) {
  if (uploadFile.raw) {
    fileList.value = [uploadFile.raw]
  }
}

function handleFileRemove() {
  fileList.value = []
}

function downloadTemplate() {
  const templates: Record<string, any[]> = {
    steps: [
      { date: '2024-01-01', steps: 8000, distance: 5.2, calories: 320 },
      { date: '2024-01-02', steps: 6500, distance: 4.3, calories: 260 },
    ],
    sleep: [
      { date: '2024-01-01', duration: 7.5, deepSleep: 1.8, lightSleep: 3.2, quality: 'good' },
      { date: '2024-01-02', duration: 6.0, deepSleep: 1.2, lightSleep: 2.8, quality: 'fair' },
    ],
    heart_rate: [
      { date: '2024-01-01', resting: 68, max: 145, avg: 78 },
      { date: '2024-01-02', resting: 72, max: 152, avg: 82 },
    ],
  }

  const data = templates[dataType.value]
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${dataType.value}_template.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('模板已下载')
}

async function handleImport() {
  const selectedFile = fileList.value[0]
  if (!selectedFile) return

  isImporting.value = true
  importResult.value = null

  try {
    await healthStore.importData(fileFormat.value, dataType.value, selectedFile)
    const progress = healthStore.importProgress
    importResult.value = {
      status: progress.status,
      importedCount: progress.importedCount,
      failedCount: progress.failedCount,
      errors: progress.errors,
    }

    if (progress.status === 'completed') {
      ElMessage.success(`导入成功，共导入 ${progress.importedCount} 条记录`)
    } else if (progress.status === 'partial') {
      ElMessage.warning(`部分导入成功：${progress.importedCount} 条成功，${progress.failedCount} 条失败`)
    }
  } catch (error: any) {
    ElMessage.error(error.message || '导入失败')
    importResult.value = {
      status: 'failed',
      importedCount: 0,
      failedCount: 0,
      errors: [error.message || '导入失败'],
    }
  } finally {
    isImporting.value = false
  }
}

function goBack() {
  router.push('/health')
}
</script>

<template>
  <div class="import-view">
    <div class="page-header">
      <div class="header-left">
        <div class="header-icon">
          <el-icon :size="26"><FirstAidKit /></el-icon>
        </div>
        <div>
          <h1>数据导入</h1>
          <p class="subtitle">上传步数、睡眠或心率数据文件，支持 JSON 和 CSV 格式。</p>
        </div>
      </div>
      <el-button @click="goBack">返回健康档案</el-button>
    </div>

    <div class="import-card">
      <el-form label-position="top" class="import-form">
        <el-form-item label="数据类型">
          <el-radio-group v-model="dataType" size="large">
            <el-radio-button value="steps">步数</el-radio-button>
            <el-radio-button value="sleep">睡眠</el-radio-button>
            <el-radio-button value="heart_rate">心率</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="文件格式">
          <el-radio-group v-model="fileFormat" size="large">
            <el-radio-button value="json">JSON</el-radio-button>
            <el-radio-button value="csv">CSV</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="选择文件">
          <el-upload
            :auto-upload="false"
            :limit="1"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
            accept=".json,.csv"
            drag
          >
            <el-icon :size="48" class="upload-icon"><Upload /></el-icon>
            <div class="upload-text">将文件拖到此处，或 <em>点击上传</em></div>
            <template #tip>
              <div class="upload-tip">只能上传 {{ fileFormat.toUpperCase() }} 文件</div>
            </template>
          </el-upload>
        </el-form-item>

        <div class="form-actions">
          <el-button @click="downloadTemplate">
            <el-icon><Download /></el-icon>
            下载模板
          </el-button>
          <el-button type="primary" :loading="isImporting" :disabled="!canImport" @click="handleImport">
            <el-icon><DataLine /></el-icon>
            {{ isImporting ? '导入中...' : '开始导入' }}
          </el-button>
        </div>
      </el-form>
    </div>

    <div v-if="importResult" class="result-card" :class="importResult.status">
      <h3>
        <span v-if="importResult.status === 'completed'">导入成功</span>
        <span v-else-if="importResult.status === 'partial'">部分导入成功</span>
        <span v-else>导入失败</span>
      </h3>
      <div class="result-stats">
        <div class="result-item">
          <span class="result-label">成功</span>
          <span class="result-value success">{{ importResult.importedCount }}</span>
        </div>
        <div class="result-item" v-if="importResult.failedCount > 0">
          <span class="result-label">失败</span>
          <span class="result-value fail">{{ importResult.failedCount }}</span>
        </div>
      </div>
      <div v-if="importResult.errors.length" class="result-errors">
        <p v-for="(err, i) in importResult.errors" :key="i">{{ err }}</p>
      </div>
      <el-button type="primary" @click="goBack" style="margin-top: 16px">查看健康档案</el-button>
    </div>

    <section class="format-guide">
      <h2>数据格式说明</h2>
      <div class="guide-grid">
        <div class="guide-item">
          <h3>步数数据</h3>
          <pre>{ "date": "2024-01-01", "steps": 8000, "distance": 5.2, "calories": 320 }</pre>
        </div>
        <div class="guide-item">
          <h3>睡眠数据</h3>
          <pre>{ "date": "2024-01-01", "duration": 7.5, "deepSleep": 1.8, "quality": "good" }</pre>
        </div>
        <div class="guide-item">
          <h3>心率数据</h3>
          <pre>{ "date": "2024-01-01", "resting": 68, "max": 145, "avg": 78 }</pre>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.import-view {
  max-width: 960px;
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
  max-width: 520px;
  color: var(--text-secondary);
  font-size: 14px;
}

.import-card {
  padding: 28px;
  border-radius: 24px;
  background: var(--surface-primary);
  border: 1px solid var(--border-soft);
  box-shadow: var(--shadow-soft);
  margin-bottom: 24px;
}

.import-form :deep(.el-form-item__label) {
  font-weight: 600;
  color: var(--text-primary);
}

.upload-icon {
  color: var(--brand-primary);
  margin-bottom: 8px;
}

.upload-text {
  color: var(--text-secondary);
  font-size: 14px;
}

.upload-text em {
  color: var(--brand-primary);
  font-style: normal;
}

.upload-tip {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.form-actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

.result-card {
  padding: 24px;
  border-radius: 20px;
  margin-bottom: 24px;
}

.result-card.completed {
  background: rgba(82, 196, 26, 0.06);
  border: 1px solid rgba(82, 196, 26, 0.2);
}

.result-card.partial {
  background: rgba(250, 173, 20, 0.06);
  border: 1px solid rgba(250, 173, 20, 0.2);
}

.result-card.failed {
  background: rgba(255, 77, 79, 0.06);
  border: 1px solid rgba(255, 77, 79, 0.2);
}

.result-card h3 {
  font-size: 18px;
  margin-bottom: 12px;
  color: var(--text-primary);
}

.result-stats {
  display: flex;
  gap: 24px;
  margin-bottom: 12px;
}

.result-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.result-label {
  color: var(--text-secondary);
  font-size: 14px;
}

.result-value.success {
  font-size: 20px;
  font-weight: 700;
  color: #52c41a;
}

.result-value.fail {
  font-size: 20px;
  font-weight: 700;
  color: #ff4d4f;
}

.result-errors {
  padding: 12px;
  border-radius: 12px;
  background: rgba(255, 77, 79, 0.06);
}

.result-errors p {
  color: #ff4d4f;
  font-size: 13px;
  line-height: 1.6;
}

.format-guide {
  padding: 24px;
  border-radius: 24px;
  background: var(--surface-primary);
  border: 1px solid var(--border-soft);
  box-shadow: var(--shadow-soft);
}

.format-guide h2 {
  font-size: 20px;
  color: var(--text-primary);
  margin-bottom: 16px;
}

.guide-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}

.guide-item {
  padding: 16px;
  border-radius: 16px;
  background: rgba(230, 244, 255, 0.5);
  border: 1px solid rgba(22, 119, 255, 0.1);
}

.guide-item h3 {
  font-size: 15px;
  color: var(--brand-primary);
  margin-bottom: 8px;
}

.guide-item pre {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
  margin: 0;
}

@media (max-width: 768px) {
  .import-view {
    padding: 16px;
  }

  .page-header {
    flex-direction: column;
  }

  .guide-grid {
    grid-template-columns: 1fr;
  }
}
</style>
