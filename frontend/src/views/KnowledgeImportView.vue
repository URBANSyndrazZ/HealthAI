<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Collection, DocumentChecked, Upload } from '@element-plus/icons-vue'
import { importKnowledgeFile, type KnowledgeFileImportResponse } from '@/api/knowledge'

const categoryOptions = [
  { label: '通用健康', value: 'health' },
  { label: '营养饮食', value: 'nutrition' },
  { label: '运动健身', value: 'exercise' },
  { label: '生活方式', value: 'lifestyle' },
  { label: '环境健康', value: 'environment' },
]

const category = ref('health')
const topic = ref('')
const chunkSize = ref(700)
const chunkOverlap = ref(80)
const dryRun = ref(false)
const fileList = ref<File[]>([])
const isImporting = ref(false)
const result = ref<KnowledgeFileImportResponse | null>(null)

const canImport = computed(() => fileList.value.length > 0 && !isImporting.value)

function isSupportedKnowledgeFile(file: File) {
  const name = file.name.toLowerCase()
  return name.endsWith('.pdf') || name.endsWith('.md') || name.endsWith('.markdown')
}

function handleFileChange(uploadFile: { raw?: File }) {
  if (!uploadFile.raw) return
  if (!isSupportedKnowledgeFile(uploadFile.raw)) {
    ElMessage.error('只能上传 PDF 或 Markdown 文件')
    fileList.value = []
    return
  }
  fileList.value = [uploadFile.raw]
  result.value = null
}

function handleFileRemove() {
  fileList.value = []
}

async function handleImport() {
  const selectedFile = fileList.value[0]
  if (!selectedFile) return

  if (chunkOverlap.value >= chunkSize.value) {
    ElMessage.error('重叠长度必须小于切片长度')
    return
  }

  isImporting.value = true
  result.value = null
  try {
    result.value = await importKnowledgeFile({
      file: selectedFile,
      category: category.value,
      topic: topic.value.trim(),
      chunkSize: chunkSize.value,
      chunkOverlap: chunkOverlap.value,
      dryRun: dryRun.value,
    })

    if (result.value.dry_run) {
      ElMessage.success(`预检完成，共解析 ${result.value.chunk_count} 个知识片段`)
    } else {
      ElMessage.success(`入库完成，共写入 ${result.value.imported_count} 个知识片段`)
    }
  } catch (error: any) {
    ElMessage.error(error.message || '知识文件入库失败')
  } finally {
    isImporting.value = false
  }
}
</script>

<template>
  <div class="knowledge-import-view">
    <div class="page-header">
      <div class="header-left">
        <div class="header-icon">
          <el-icon :size="26"><Collection /></el-icon>
        </div>
        <div>
          <h1>知识库入库</h1>
          <p class="subtitle">管理人员上传健康指南 PDF 或 Markdown，系统自动完成解析、切片、向量化并写入知识库。</p>
        </div>
      </div>
      <el-tag type="info" effect="plain">管理端</el-tag>
    </div>

    <div class="import-layout">
      <section class="panel">
        <el-form label-position="top" class="knowledge-form">
          <el-form-item label="知识文件">
            <el-upload
              :auto-upload="false"
              :limit="1"
              :on-change="handleFileChange"
              :on-remove="handleFileRemove"
              accept=".pdf,.md,.markdown,application/pdf,text/markdown,text/x-markdown,text/plain"
              drag
            >
              <el-icon :size="48" class="upload-icon"><Upload /></el-icon>
              <div class="upload-text">拖入 PDF / Markdown，或 <em>点击选择文件</em></div>
              <template #tip>
                <div class="upload-tip">建议上传权威指南、专家共识或机构公开资料，支持 .pdf、.md、.markdown，单个文件不超过 30MB。</div>
              </template>
            </el-upload>
          </el-form-item>

          <div class="form-grid">
            <el-form-item label="知识分类">
              <el-select v-model="category" size="large">
                <el-option
                  v-for="item in categoryOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="主题标签">
              <el-input v-model="topic" size="large" placeholder="如 sleep、aerobic、blood_pressure" />
            </el-form-item>

            <el-form-item label="切片长度">
              <el-input-number v-model="chunkSize" :min="200" :max="2000" :step="100" size="large" />
            </el-form-item>

            <el-form-item label="重叠长度">
              <el-input-number v-model="chunkOverlap" :min="0" :max="500" :step="20" size="large" />
            </el-form-item>
          </div>

          <div class="option-row">
            <el-switch v-model="dryRun" />
            <span>仅预检解析结果，不写入向量数据库</span>
          </div>

          <div class="form-actions">
            <el-button type="primary" :loading="isImporting" :disabled="!canImport" @click="handleImport">
              <el-icon><DocumentChecked /></el-icon>
              {{ isImporting ? '处理中...' : dryRun ? '开始预检' : '上传并入库' }}
            </el-button>
          </div>
        </el-form>
      </section>

      <section class="panel status-panel">
        <h2>入库流程</h2>
        <div class="step-list">
          <div class="step-item">
            <span>1</span>
            <p>解析 PDF 文本或读取 Markdown 内容</p>
          </div>
          <div class="step-item">
            <span>2</span>
            <p>清洗页码、空行和低价值文本</p>
          </div>
          <div class="step-item">
            <span>3</span>
            <p>按长度和重叠窗口切分知识片段</p>
          </div>
          <div class="step-item">
            <span>4</span>
            <p>调用 BGE-M3 生成向量并写入 Elasticsearch</p>
          </div>
        </div>
      </section>
    </div>

    <section v-if="result" class="result-panel" :class="{ preview: result.dry_run }">
      <div>
        <h2>{{ result.dry_run ? '预检完成' : '入库完成' }}</h2>
        <p>{{ result.title }}</p>
      </div>
      <div class="result-grid">
        <div>
          <span>类型</span>
          <strong>{{ result.source_type }}</strong>
        </div>
        <div>
          <span>文件名</span>
          <strong>{{ result.filename }}</strong>
        </div>
        <div>
          <span>索引</span>
          <strong>{{ result.index_name }}</strong>
        </div>
        <div>
          <span>知识片段</span>
          <strong>{{ result.chunk_count }}</strong>
        </div>
        <div>
          <span>写入数量</span>
          <strong>{{ result.imported_count }}</strong>
        </div>
      </div>
      <div v-if="result.preview_ids.length" class="id-preview">
        <span>片段 ID 预览</span>
        <code>{{ result.preview_ids.join(' / ') }}</code>
      </div>
    </section>
  </div>
</template>

<style scoped>
.knowledge-import-view {
  max-width: 1120px;
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
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, rgba(22, 119, 255, 0.16), rgba(19, 194, 194, 0.18));
  color: var(--brand-primary);
  box-shadow: var(--shadow-soft);
}

.header-left h1 {
  font-size: 28px;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.subtitle {
  max-width: 640px;
  color: var(--text-secondary);
  font-size: 14px;
}

.import-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 20px;
  align-items: start;
}

.panel,
.result-panel {
  padding: 24px;
  border-radius: 8px;
  background: var(--surface-primary);
  border: 1px solid var(--border-soft);
  box-shadow: var(--shadow-soft);
}

.knowledge-form :deep(.el-form-item__label) {
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
  color: var(--text-secondary);
  font-size: 12px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.option-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 2px 0 18px;
  color: var(--text-secondary);
  font-size: 14px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
}

.status-panel h2,
.result-panel h2 {
  font-size: 18px;
  color: var(--text-primary);
  margin-bottom: 16px;
}

.step-list {
  display: grid;
  gap: 14px;
}

.step-item {
  display: grid;
  grid-template-columns: 30px 1fr;
  gap: 10px;
  align-items: center;
}

.step-item span {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(22, 119, 255, 0.1);
  color: var(--brand-primary);
  font-weight: 700;
}

.step-item p {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.5;
}

.result-panel {
  margin-top: 20px;
  border-color: rgba(82, 196, 26, 0.28);
  background: rgba(82, 196, 26, 0.05);
}

.result-panel.preview {
  border-color: rgba(250, 173, 20, 0.3);
  background: rgba(250, 173, 20, 0.06);
}

.result-panel > div:first-child p {
  color: var(--text-secondary);
  font-size: 14px;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.result-grid div {
  padding: 14px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(22, 119, 255, 0.08);
}

.result-grid span,
.id-preview span {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
  margin-bottom: 6px;
}

.result-grid strong {
  color: var(--text-primary);
  font-size: 16px;
  word-break: break-word;
}

.id-preview {
  margin-top: 14px;
}

.id-preview code {
  display: block;
  padding: 12px;
  border-radius: 8px;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(22, 119, 255, 0.08);
  word-break: break-all;
  line-height: 1.6;
}

@media (max-width: 960px) {
  .import-layout,
  .form-grid,
  .result-grid {
    grid-template-columns: 1fr;
  }

  .page-header {
    flex-direction: column;
  }
}

@media (max-width: 640px) {
  .knowledge-import-view {
    padding: 16px;
  }
}
</style>
