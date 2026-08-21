<script setup>
import { computed } from 'vue'
import { fmtG, locationLabel } from '../api'

const props = defineProps({ spools: { type: Array, required: true } })

const range = (lo, hi, unit) => (lo == null && hi == null ? null : lo != null && hi != null ? `${lo}–${hi} ${unit}` : `${lo ?? hi} ${unit}`)

// [label, getter, { best: 'max' | 'min' }] — best marks the winning column(s) for numeric rows.
const ROWS = [
  ['Brand', (s) => s.brand],
  ['Material', (s) => s.material],
  ['Form', (s) => (s.spool_type === 'refill' ? 'Refill' : 'Spool')],
  ['Location', (s) => (s.location === 'stored' && !s.opened ? 'Sealed' : locationLabel(s.location))],
  ['Remaining', (s) => `${fmtG(s.remaining_g)} (${s.remaining_pct}%)`, { num: (s) => s.remaining_g, best: 'max' }],
  ['Strength (bending)', (s) => (s.strength_mpa == null ? null : `${s.strength_mpa} MPa`), { num: (s) => s.strength_mpa, best: 'max' }],
  ['Stiffness (modulus)', (s) => (s.stiffness_mpa == null ? null : `${s.stiffness_mpa} MPa`), { num: (s) => s.stiffness_mpa, best: 'max' }],
  ['Toughness (impact)', (s) => (s.toughness_kj_m2 == null ? null : `${s.toughness_kj_m2} kJ/m²`), { num: (s) => s.toughness_kj_m2, best: 'max' }],
  ['Heat resistance (HDT)', (s) => (s.heat_resistance_c == null ? null : `${s.heat_resistance_c} °C`), { num: (s) => s.heat_resistance_c, best: 'max' }],
  ['Print shrinkage (1 = least)', (s) => (s.shrinkage_rank == null ? null : `${s.shrinkage_rank} / 7`), { num: (s) => s.shrinkage_rank, best: 'min' }],
  ['Nozzle temp', (s) => range(s.nozzle_temp_min_c, s.nozzle_temp_max_c, '°C')],
  ['Bed temp', (s) => range(s.bed_temp_min_c, s.bed_temp_max_c, '°C')],
  ['Drying', (s) => (s.drying_temp_c == null ? null : `${s.drying_temp_c} °C${s.drying_time_h ? ` · ${s.drying_time_h} h` : ''}`)],
  ['Density', (s) => (s.density_g_cm3 == null ? null : `${s.density_g_cm3} g/cm³`)],
]

const rows = computed(() =>
  ROWS.map(([label, get, opts]) => {
    const cells = props.spools.map((s) => ({ text: get(s), num: opts?.num ? opts.num(s) : null, best: false }))
    if (opts?.best && props.spools.length > 1) {
      const nums = cells.map((c) => c.num).filter((n) => n != null)
      if (nums.length > 1) {
        const target = opts.best === 'max' ? Math.max(...nums) : Math.min(...nums)
        if (Math.max(...nums) !== Math.min(...nums)) cells.forEach((c) => { c.best = c.num === target })
      }
    }
    return { label, cells }
  }).filter((r) => r.cells.some((c) => c.text != null)),
)
</script>
<template>
  <div class="wrap">
    <table class="cmp" data-test="compare-table">
      <thead>
        <tr>
          <th></th>
          <th v-for="s in spools" :key="s.id">
            <div class="img"><img v-if="s.image_url" :src="s.image_url" :alt="s.colour_name" /><span v-else class="ph" :style="{ background: s.colour_hex ? '#' + s.colour_hex : 'var(--panel-2)' }"></span></div>
            <div class="micro">{{ s.subtype }}</div>
            <div class="name"><span class="swatch" :style="{ background: '#' + (s.colour_hex || '333') }"></span>{{ s.colour_name }}</div>
            <router-link :to="`/spools/${s.id}`" class="small">Open →</router-link>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.label">
          <th scope="row">{{ r.label }}</th>
          <td v-for="(c, i) in r.cells" :key="i" :class="{ best: c.best, none: c.text == null }">{{ c.text ?? '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
<style scoped>
.wrap { overflow-x: auto; }
.cmp { width: 100%; border-collapse: collapse; font-size: 15px; }
.cmp thead th { text-align: left; vertical-align: bottom; padding: 0 12px 12px; border-bottom: 1px solid var(--line); text-transform: none; letter-spacing: 0; font-size: 15px; min-width: 160px; }
.cmp thead th:first-child { min-width: 0; }
.cmp tbody th { text-align: left; font-size: 14px; color: var(--muted); font-weight: 600; padding: 9px 12px; white-space: nowrap; border-bottom: 1px solid var(--line); letter-spacing: 0; text-transform: none; }
.cmp td { padding: 9px 12px; border-bottom: 1px solid var(--line); font-variant-numeric: tabular-nums; }
.cmp td.best { color: var(--pass); font-weight: 600; }
.cmp td.none { color: var(--muted); }
.cmp tbody tr:hover td, .cmp tbody tr:hover th { background: var(--panel-2); }
.img { width: 72px; height: 72px; border-radius: 6px; overflow: hidden; background: #fff; margin-bottom: 8px; display: flex; align-items: center; justify-content: center; }
.img img { width: 100%; height: 100%; object-fit: contain; }
.ph { width: 100%; height: 100%; display: block; }
.name { font-weight: 600; font-size: 16px; display: flex; align-items: center; gap: 8px; color: var(--text); }
.small { font-size: 13px; }
</style>
