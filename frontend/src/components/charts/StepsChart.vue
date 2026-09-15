<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  MarkLineComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { HealthData } from '@/stores/health'

use([BarChart, TitleComponent, TooltipComponent, GridComponent, MarkLineComponent, CanvasRenderer])

const props = defineProps<{
  data: HealthData[]
  title?: string
  height?: string
}>()

const option = computed(() => {
  const dates = props.data.map(d => d.date?.slice(5) || '')
  const steps = props.data.map(d => d.steps || 0)

  return {
    title: props.title
      ? {
          text: props.title,
          left: 'center',
          textStyle: { fontSize: 14, fontWeight: 600, color: '#1d2129' },
        }
      : undefined,
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#e5e6eb',
      textStyle: { color: '#1d2129', fontSize: 13 },
      formatter: (params: any) => {
        const p = params[0]
        return `<div style="font-weight:600">${p.name}</div>步数：<b>${p.value?.toLocaleString()}</b> 步`
      },
    },
    grid: { left: 50, right: 20, top: props.title ? 46 : 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: '#f2f3f5' } },
      axisLabel: { color: '#86909c', fontSize: 11, formatter: (v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v },
    },
    series: [
      {
        type: 'bar',
        data: steps,
        barWidth: props.data.length <= 7 ? 28 : undefined,
        itemStyle: {
          borderRadius: [6, 6, 0, 0],
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: '#4080ff' },
              { offset: 1, color: '#69b1ff' },
            ],
          },
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { color: '#ff7875', type: 'dashed', width: 1.5 },
          label: { formatter: '目标 8000', color: '#ff7875', fontSize: 11, position: 'insideEndTop' },
          data: [{ yAxis: 8000 }],
        },
      },
    ],
  }
})
</script>

<template>
  <VChart :option="option" :style="{ height: height || '280px' }" autoresize />
</template>
