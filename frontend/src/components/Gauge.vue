<script setup>
import { computed } from 'vue'
const props = defineProps({ pct: { type: Number, default: 0 }, size: { type: Number, default: 64 }, stroke: { type: Number, default: 7 }, cls: String })
const r = computed(() => (props.size - props.stroke) / 2)
const c = computed(() => 2 * Math.PI * r.value)
const dash = computed(() => `${(Math.max(0, Math.min(100, props.pct)) / 100) * c.value} ${c.value}`)
</script>
<template>
  <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" class="gauge" :class="cls">
    <circle :cx="size/2" :cy="size/2" :r="r" fill="none" stroke="var(--line)" :stroke-width="stroke" />
    <circle :cx="size/2" :cy="size/2" :r="r" fill="none" class="arc" :stroke-width="stroke" stroke-linecap="round" :stroke-dasharray="dash" :transform="`rotate(-90 ${size/2} ${size/2})`" />
    <text :x="size/2" :y="size/2" text-anchor="middle" dominant-baseline="central" class="num lbl">{{ Math.round(pct) }}%</text>
  </svg>
</template>
<style scoped>
.arc { stroke: var(--edge); transition: stroke-dasharray .5s ease; }
.gauge.warn .arc { stroke: var(--warn); } .gauge.fail .arc { stroke: var(--fail); }
.lbl { fill: var(--text); font-size: 13px; font-weight: 600; }
</style>
