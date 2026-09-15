<script setup lang="ts">
import { computed } from 'vue'
import { ElCard, ElTag, ElTimeline, ElTimelineItem, ElButton, ElSpace } from 'element-plus'
import { Timer, Trophy, Warning, Check, CircleCheck, VideoPlay } from '@element-plus/icons-vue'
import type { ExerciseResponse } from '@/api/agents'

interface Props {
  result: ExerciseResponse['data']
}

const props = defineProps<Props>()

// 获取强度颜色
const getIntensityColor = (intensity: string) => {
  const colors: Record<string, string> = {
    'low': '#67c23a',
    'medium': '#e6a23c',
    'high': '#f56c6c'
  }
  return colors[intensity] || '#909399'
}

// 获取强度标签
const getIntensityLabel = (intensity: string) => {
  const labels: Record<string, string> = {
    'low': '低强度',
    'medium': '中等强度',
    'high': '高强度'
  }
  return labels[intensity] || intensity
}

// 获取运动类型图标
const getExerciseIcon = (type: string) => {
  const icons: Record<string, string> = {
    '跑步': '🏃',
    '游泳': '🏊',
    '骑行': '🚴',
    '瑜伽': '🧘',
    '力量训练': '💪',
    '有氧运动': '🤸',
    '球类运动': '⚽',
    '户外': '🏔️'
  }
  // 匹配关键词
  for (const [key, icon] of Object.entries(icons)) {
    if (type.includes(key)) return icon
  }
  return '🏃'
}
</script>

<template>
  <div class="exercise-result">
    <!-- 健身水平卡片 -->
    <ElCard class="level-card" shadow="hover">
      <div class="level-header">
        <div class="level-icon">🏆</div>
        <div class="level-info">
          <div class="level-title">当前体能水平</div>
          <div class="level-value">
            {{ result.fitness_level === 'beginner' ? '初学者' :
               result.fitness_level === 'intermediate' ? '中级' : '高级' }}
          </div>
        </div>
      </div>
    </ElCard>

    <!-- 运动列表 -->
    <ElCard class="exercises-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <Trophy />
          <span>推荐运动 ({{ result.exercises.length }}项)</span>
        </div>
      </template>

      <ElTimeline>
        <ElTimelineItem
          v-for="(exercise, index) in result.exercises"
          :key="index"
          :type="exercise.intensity === 'high' ? 'danger' : exercise.intensity === 'medium' ? 'warning' : 'success'"
          :icon="Check"
        >
          <div class="exercise-item">
            <div class="exercise-header">
              <div class="exercise-icon">{{ getExerciseIcon(exercise.name) }}</div>
              <div class="exercise-info">
                <div class="exercise-name">{{ exercise.name }}</div>
                <div class="exercise-tags">
                  <ElTag size="small" effect="plain">{{ exercise.type }}</ElTag>
                  <ElTag size="small" :color="getIntensityColor(exercise.intensity)" effect="dark">
                    {{ getIntensityLabel(exercise.intensity) }}
                  </ElTag>
                  <ElTag size="small" type="info" effect="plain">{{ exercise.duration_min }}分钟</ElTag>
                </div>
              </div>
            </div>
            <div v-if="exercise.calories_per_hour" class="exercise-calories">
              🔥 约 {{ Math.round(exercise.calories_per_hour * exercise.duration_min / 60) }} 千卡
            </div>

            <div v-if="exercise.benefits" class="exercise-benefits">
              ✓ {{ exercise.benefits }}
            </div>

            <div v-if="exercise.precautions" class="exercise-precautions">
              ⚠ 注意事项：{{ exercise.precautions }}
            </div>
          </div>
        </ElTimelineItem>
      </ElTimeline>

      <!-- 环境适配建议 -->
      <div v-if="result.env_adjustments && result.env_adjustments.length > 0" class="env-adjustments">
        <ElDivider />
        <div class="adjustments-title">🌤️ 环境适配建议</div>
        <div class="adjustments-list">
          <ElAlert
            v-for="(adjustment, index) in result.env_adjustments"
            :key="index"
            :title="adjustment"
            type="info"
            :closable="false"
            show-icon
            class="adjustment-alert"
          />
        </div>
      </div>

      <!-- 安全约束 -->
      <div v-if="result.safety_constraints && result.safety_constraints.length > 0" class="safety-constraints">
        <ElDivider />
        <div class="constraints-title">⚠️ 安全注意事项</div>
        <div class="constraints-list">
          <ElAlert
            v-for="(constraint, index) in result.safety_constraints"
            :key="index"
            :title="constraint"
            type="warning"
            :closable="false"
            show-icon
            class="constraint-alert"
          />
        </div>
      </div>
    </ElCard>
  </div>
</template>

<style scoped lang="scss">
.exercise-result {
  display: flex;
  flex-direction: column;
  gap: 16px;

  :deep(.el-card) {
    border-radius: 12px;
  }
}

// 健身水平卡片
.level-card {
  .level-header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 16px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 8px;
    color: #fff;

    .level-icon {
      width: 48px;
      height: 48px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.2);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
    }

    .level-info {
      flex: 1;

      .level-title {
        font-size: 14px;
        opacity: 0.9;
        margin-bottom: 4px;
      }

      .level-value {
        font-size: 20px;
        font-weight: 600;
      }
    }
  }
}

// 运动列表卡片
.exercises-card {
  :deep(.el-card__header) {
    padding: 16px 20px;
  }

  .card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    color: #303133;
  }
}

// 运动项
.exercise-item {
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 12px;
  transition: all 0.3s;

  &:hover {
    background: #e4e7ed;
  }

  .exercise-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;

    .exercise-icon {
      width: 40px;
      height: 40px;
      border-radius: 8px;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
    }

    .exercise-info {
      flex: 1;

      .exercise-name {
        font-size: 16px;
        font-weight: 600;
        color: #303133;
        margin-bottom: 6px;
      }

      .exercise-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }
    }
  }

  .exercise-calories {
    font-size: 13px;
    color: #e6a23c;
    margin-bottom: 8px;
  }

  .exercise-benefits {
    font-size: 13px;
    color: #67c23a;
    margin-bottom: 8px;
  }

  .exercise-precautions {
    font-size: 13px;
    color: #f56c6c;
  }
}

// 环境适配建议
.env-adjustments {
  .adjustments-title {
    font-size: 16px;
    font-weight: 600;
    color: #303133;
    margin-bottom: 12px;
  }

  .adjustments-list {
    display: flex;
    flex-direction: column;
    gap: 8px;

    .adjustment-alert {
      margin: 0;
    }
  }
}

// 安全约束
.safety-constraints {
  .constraints-title {
    font-size: 16px;
    font-weight: 600;
    color: #f56c6c;
    margin-bottom: 12px;
  }

  .constraints-list {
    display: flex;
    flex-direction: column;
    gap: 8px;

    .constraint-alert {
      margin: 0;
    }
  }
}

// 响应式
@media (max-width: 768px) {
  .level-card {
    .level-header {
      flex-direction: column;
      text-align: center;
    }
  }

  .exercise-item {
    .exercise-header {
      flex-direction: column;
      align-items: flex-start;
    }
  }
}
</style>
