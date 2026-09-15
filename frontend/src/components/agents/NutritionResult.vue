<script setup lang="ts">
import { computed } from 'vue'
import { ElCard, ElTag, ElProgress, ElDivider } from 'element-plus'
import { Food, KnifeFork, Warning, Trophy } from '@element-plus/icons-vue'
import type { NutritionResponse } from '@/api/agents'

interface Props {
  result: NutritionResponse['data']
}

const props = defineProps<Props>()

// 计算总热量占比（基于2000千卡标准）
const caloriePercentage = computed(() => {
  return Math.min(Math.round((props.result.total.calories / 2000) * 100), 100)
})

// 获取评分颜色
function getScoreColor(score: number): string {
  if (score >= 8) return '#67c23a'
  if (score >= 6) return '#e6a23c'
  return '#f56c6c'
}

// 获取评分标签
function getScoreLabel(score: number): string {
  if (score >= 9) return '优秀'
  if (score >= 8) return '良好'
  if (score >= 7) return '中等'
  if (score >= 6) return '及格'
  return '需改善'
}

// 获取警告类型
function getWarningType(warning: string): 'danger' | 'warning' | 'info' {
  if (warning.includes('过敏') || warning.includes('高')) return 'danger'
  if (warning.includes('中等') || warning.includes('较多')) return 'warning'
  return 'info'
}
</script>

<template>
  <div class="nutrition-result">
    <!-- 评分卡片 -->
    <ElCard class="score-card" shadow="hover">
      <div class="score-header">
        <div class="score-circle" :style="{ borderColor: getScoreColor(result.score) }">
          <span class="score-value" :style="{ color: getScoreColor(result.score) }">{{ result.score }}</span>
          <span class="score-label">分</span>
        </div>
        <div class="score-info">
          <div class="score-title">{{ getScoreLabel(result.score) }}</div>
          <div class="score-desc">基于营养成分和均衡性评估</div>
        </div>
      </div>

      <ElDivider />

      <!-- 营养总览 -->
      <div class="nutrition-summary">
        <div class="summary-title">
          <ElIcon><KnifeFork /></ElIcon>营养总览
        </div>
        <div class="nutrition-grid">
          <div class="nutrition-item">
            <div class="item-value" :class="{ high: result.total.calories > 800 }">
              {{ result.total.calories }}
            </div>
            <div class="item-label">热量 (kcal)</div>
          </div>
          <div class="nutrition-item">
            <div class="item-value">{{ result.total.protein }}g</div>
            <div class="item-label">蛋白质</div>
          </div>
          <div class="nutrition-item">
            <div class="item-value">{{ result.total.fat }}g</div>
            <div class="item-label">脂肪</div>
          </div>
          <div class="nutrition-item">
            <div class="item-value">{{ result.total.carbs }}g</div>
            <div class="item-label">碳水</div>
          </div>
          <div v-if="result.total.fiber" class="nutrition-item">
            <div class="item-value">{{ result.total.fiber }}g</div>
            <div class="item-label">膳食纤维</div>
          </div>
          <div v-if="result.total.sodium" class="nutrition-item">
            <div class="item-value">{{ result.total.sodium }}mg</div>
            <div class="item-label">钠含量</div>
          </div>
        </div>
      </div>
    </ElCard>

    <!-- 食物列表 -->
    <ElCard v-if="result.foods.length > 0" class="foods-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <ElIcon><Food /></ElIcon>
          <span>食物明细 ({{ result.foods.length }}种)</span>
        </div>
      </template>

      <div class="foods-list">
        <div v-for="(food, index) in result.foods" :key="index" class="food-item">
          <div class="food-info">
            <div class="food-name">{{ food.name }}</div>
            <div class="food-amount">{{ food.grams }}g</div>
          </div>
          <div class="food-nutrition">
            <div class="nutrition-tag">{{ food.calories }} kcal</div>
            <div class="nutrition-tag protein">蛋{{ food.protein }}g</div>
            <div class="nutrition-tag fat">脂{{ food.fat }}g</div>
            <div class="nutrition-tag carbs">碳{{ food.carbs }}g</div>
          </div>
        </div>
      </div>
    </ElCard>

    <!-- 健康建议 -->
    <ElCard v-if="result.advice" class="advice-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <ElIcon><Trophy /></ElIcon>
          <span>健康建议</span>
        </div>
      </template>

      <div class="advice-content">{{ result.advice }}</div>
    </ElCard>

    <!-- 注意事项 -->
    <ElCard v-if="result.warnings.length > 0" class="warnings-card" shadow="hover">
      <template #header>
        <div class="card-header warning">
          <ElIcon><Warning /></ElIcon>
          <span>注意事项</span>
        </div>
      </template>

      <div class="warnings-list">
        <ElTag
          v-for="(warning, index) in result.warnings"
          :key="index"
          :type="getWarningType(warning)"
          effect="dark"
          class="warning-tag"
        >
          {{ warning }}
        </ElTag>
      </div>
    </ElCard>
  </div>
</template>

<style scoped lang="scss">
.nutrition-result {
  display: flex;
  flex-direction: column;
  gap: 16px;

  :deep(.el-card) {
    border-radius: 12px;
  }
}

// 评分卡片
.score-card {
  .score-header {
    display: flex;
    align-items: center;
    gap: 24px;
    padding: 16px;
  }

  .score-circle {
    width: 100px;
    height: 100px;
    border-radius: 50%;
    border: 4px solid;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, #f5f7fa 0%, #e4e7ed 100%);

    .score-value {
      font-size: 36px;
      font-weight: 700;
      line-height: 1;
    }

    .score-label {
      font-size: 14px;
      color: #909399;
    }
  }

  .score-info {
    flex: 1;

    .score-title {
      font-size: 24px;
      font-weight: 600;
      color: #303133;
      margin-bottom: 8px;
    }

    .score-desc {
      font-size: 14px;
      color: #909399;
    }
  }
}

// 营养总览
.nutrition-summary {
  padding: 16px;

  .summary-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 16px;
    font-weight: 600;
    color: #303133;
    margin-bottom: 16px;
  }

  .nutrition-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 16px;
  }

  .nutrition-item {
    text-align: center;
    padding: 16px;
    background: #f5f7fa;
    border-radius: 8px;
    transition: all 0.3s;

    &:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }

    .item-value {
      font-size: 24px;
      font-weight: 700;
      color: #303133;
      margin-bottom: 4px;

      &.high {
        color: #f56c6c;
      }
    }

    .item-label {
      font-size: 12px;
      color: #909399;
    }
  }
}

// 食物列表
.foods-card {
  .card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    color: #303133;
  }

  .foods-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .food-item {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 16px;
    background: #f5f7fa;
    border-radius: 8px;
    transition: all 0.2s;

    &:hover {
      background: #e4e7ed;
    }
  }

  .food-info {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 12px;

    .food-name {
      font-size: 15px;
      font-weight: 500;
      color: #303133;
    }

    .food-amount {
      font-size: 13px;
      color: #909399;
      background: #fff;
      padding: 2px 8px;
      border-radius: 4px;
    }
  }

  .food-nutrition {
    display: flex;
    gap: 8px;

    .nutrition-tag {
      font-size: 12px;
      color: #606266;
      background: #fff;
      padding: 4px 8px;
      border-radius: 4px;

      &.protein {
        color: #67c23a;
        background: #f0f9eb;
      }

      &.fat {
        color: #e6a23c;
        background: #fdf6ec;
      }

      &.carbs {
        color: #409eff;
        background: #ecf5ff;
      }
    }
  }
}

// 建议卡片
.advice-card {
  .card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    color: #303133;
  }

  .advice-content {
    font-size: 14px;
    line-height: 1.8;
    color: #606266;
    white-space: pre-line;
  }
}

// 警告卡片
.warnings-card {
  .card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    color: #f56c6c;

    &.warning {
      color: #e6a23c;
    }
  }

  .warnings-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;

    .warning-tag {
      font-size: 13px;
    }
  }
}

// 响应式
@media (max-width: 768px) {
  .score-card {
    .score-header {
      flex-direction: column;
      gap: 16px;
    }

    .score-circle {
      width: 80px;
      height: 80px;

      .score-value {
        font-size: 28px;
      }
    }

    .score-info {
      text-align: center;

      .score-title {
        font-size: 20px;
      }
    }
  }

  .foods-card {
    .food-item {
      flex-direction: column;
      gap: 12px;
    }

    .food-info {
      flex-direction: column;
      align-items: flex-start;
      gap: 4px;
    }

    .food-nutrition {
      flex-wrap: wrap;
    }
  }
}
</style>
