<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { HealthData } from '@/stores/health'

use([LineChart, TitleComponent, TooltipComponent, GridComponent, LegendComponent, MarkAreaComponent, CanvasRenderer])

const props = defineProps<{
  data: HealthData[]
  title?: string
  height?: string
}>()

const option = computed(() => {
  const dates = props.data.map(d => d.date?.slice(5) || '')
  const resting = props.data.map(d => d.resting || null)
  const avg = props.data.map(d => d.avg || null)
  const max = props.data.map(d => d.max || null)

  const hasAvg = avg.some(v => v !== null)
  const hasMax = max.some(v => v !== null)

  const series: any[] = [
    {
      name: '静息心率',
      type: 'line',
      data: resting,
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { width: 2.5, color: '#ff7875' },
      itemStyle: { color: '#ff7875' },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(255,120,117,0.25)' },
            { offset: 1, color: 'rgba(255,120,117,0.02)' },
          ],
        },
      },
      markArea: {
        silent: true,
        itemStyle: { color: 'rgba(250,173,20,0.06)' },
        data: [[{ yAxis: 60 }, { yAxis: 100 }]],
        label: { show: true, position: 'insideTopRight', formatter: '正常 60-100', color: '#faad14', fontSize: 10 },
      },
    },
  ]

  if (hasAvg) {
    series.push({
      name: '平均心率',
      type: 'line',
      data: avg,
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2, color: '#ffa940', type: 'dashed' },
      itemStyle: { color: '#ffa940' },
    })
  }

  if (hasMax) {
    series.push({
      name: '最高心率',
      type: 'line',
      data: max,
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2, color: '#ff9c6e', type: 'dotted' },
      itemStyle: { color: '#ff9c6e' },
    })
  }

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
        let html = `<div style="font-weight:600">${params[0].name}</div>`
        for (const p of params) {
          if (p.value != null) {
            html += `${p.marker} ${p.seriesName}：<b>${p.value}</b> bpm<br/>`
          }
        }
        return html
      },
    },
    legend: (hasAvg || hasMax)
      ? {
          bottom: 0,
          textStyle: { fontSize: 11, color: '#86909c' },
          itemWidth: 16,
          itemHeight: 8,
        }
      : undefined,
    grid: {
      left: 46,
      right: 20,
      top: props.title ? 46 : 20,
      bottom: (hasAvg || hasMax) ? 36 : 30,
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#e5e6eb' } },
      axisTick: { show: false },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      name: 'bpm',
      nameTextStyle: { color: '#86909c', fontSize: 11 },
      splitLine: { lineStyle: { color: '#f2f3f5' } },
      axisLabel: { color: '#86909c', fontSize: 11 },
    },
    series,
  }
})
</script>

<template>
  <VChart :option="option" :style="{ height: height || '280px' }" autoresize />
</template>
