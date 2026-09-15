<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  MarkAreaComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { HealthData } from '@/stores/health'

use([BarChart, TitleComponent, TooltipComponent, GridComponent, MarkAreaComponent, CanvasRenderer])

const props = defineProps<{
  data: HealthData[]
  title?: string
  height?: string
}>()

const option = computed(() => {
  const dates = props.data.map(d => d.date?.slice(5) || '')
  const deepSleep = props.data.map(d => d.deepSleep || 0)
  const lightSleep = props.data.map(d => d.lightSleep || 0)

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
        const date = params[0].name
        const deep = params.find((p: any) => p.seriesName === '深度睡眠')?.value || 0
        const light = params.find((p: any) => p.seriesName === '浅度睡眠')?.value || 0
        const total = deep + light
        return `<div style="font-weight:600">${date}</div>总时长：<b>${total.toFixed(1)}</b> 小时<br/>深度：${deep.toFixed(1)}h / 浅度：${light.toFixed(1)}h`
      },
    },
    grid: { left: 46, right: 20, top: props.title ? 46 : 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      name: '小时',
      nameTextStyle: { color: '#86909c', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f2f3f5' } },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    series: [
      {
        name: '深度睡眠',
        type: 'bar',
        stack: 'sleep',
        data: deepSleep,
        barWidth: props.data.length <= 7 ? 28 : undefined,
        itemStyle: {
          borderRadius: [0, 0, 0, 0],
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: '#36cfc9' },
              { offset: 1, color: '#36cfc9' },
            ],
          },
        },
        markArea: {
          silent: true,
          itemStyle: { color: 'rgba(82,196,26,0.08)' },
          data: [[{ yAxis: 7 }, { yAxis: 9 }]],
          label: { show: true, position: 'insideTopRight', formatter: '推荐 7-9h', color: '#52c41a', fontSize: 10 },
        },
      },
      {
        name: '浅度睡眠',
        type: 'bar',
        stack: 'sleep',
        data: lightSleep,
        itemStyle: {
          borderRadius: [6, 6, 0, 0],
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: '#73d13d' },
              { offset: 1, color: '#95de64' },
            ],
          },
        },
      },
    ],
  }
})
</script>

<template>
  <VChart :option="option" :style="{ height: height || '280px' }" autoresize />
</template>
