<script setup>
import { computed } from 'vue'
import { useStore } from '../store'
import { fmtG, locationLabel, levelClass } from '../api'
import Gauge from './Gauge.vue'

const props = defineProps({ spool: { type: Object, required: true }, compact: Boolean, selectable: Boolean, selected: Boolean })
const emit = defineEmits(['toggle'])
const store = useStore()
const cls = computed(() => levelClass(props.spool.remaining_pct, store.thresholds))
const inAms = computed(() => props.spool.location?.startsWith('ams:'))
const SPECS = [
  ['strength_mpa', 'Bend', 'Strength (bending)', 'MPa'],
  ['stiffness_mpa', 'Stiff', 'Stiffness (modulus)', 'MPa'],
  ['toughness_kj_m2', 'Impact', 'Toughness (impact)', 'kJ/m²'],
  ['heat_resistance_c', 'Heat', 'Heat resistance (HDT)', '°C'],
  ['shrinkage_rank', 'Shrink', 'Print shrinkage rank (1 = least, 7 = most)', '/7'],
]
const specs = computed(() => SPECS.filter(([k]) => props.spool[k] != null).map(([k, label, title, unit]) => ({ label, title, value: `${props.spool[k]} ${unit}` })))
</script>
<template>
  <component :is="selectable ? 'div' : 'router-link'" :to="selectable ? undefined : `/spools/${spool.id}`" class="card" :class="[cls, { ams: inAms, selectable, selected }]" :data-test="`spool-${spool.id}`" @click="selectable && emit('toggle', spool.id)">
    <span v-if="selectable" class="tick" :class="{ on: selected }" aria-hidden="true">{{ selected ? '✓' : '' }}</span>
    <div class="img">
      <img v-if="spool.image_url" :src="spool.image_url" :alt="spool.colour_name" loading="lazy" />
      <span v-else class="ph" :style="{ background: spool.colour_hex ? '#' + spool.colour_hex : 'var(--panel-2)' }"></span>
    </div>
    <div class="body">
      <div class="top">
        <span class="micro">{{ spool.subtype }}</span>
        <span v-if="inAms" class="badge edge">{{ locationLabel(spool.location) }}</span>
        <span v-else-if="spool.location === 'stored' && !spool.opened" class="badge">Sealed</span>
        <span v-else class="badge">{{ locationLabel(spool.location) }}</span>
      </div>
      <div class="name"><span class="swatch" :style="{ background: '#' + (spool.colour_hex || '333') }"></span>{{ spool.colour_name }}</div>
      <div class="meta muted">{{ spool.brand }} · {{ spool.material }} · {{ spool.spool_type === 'refill' ? 'Refill' : 'Spool' }}</div>
      <div v-if="specs.length" class="meta muted specs"><span v-for="sp in specs" :key="sp.label" :title="sp.title">{{ sp.label }} <b class="num">{{ sp.value }}</b></span></div>
      <div class="bottom">
        <div class="grow">
          <div class="bar" :class="cls"><i :style="{ width: spool.remaining_pct + '%' }"></i></div>
          <div class="nums"><span class="num">{{ fmtG(spool.remaining_g) }}</span> <span class="muted">of {{ fmtG(spool.starting_weight_g) }}</span>
            <span v-if="spool.ams_divergent" class="badge warn" title="AMS estimate disagrees with calculated remaining">AMS {{ spool.ams_remaining_pct }}%</span>
          </div>
        </div>
        <Gauge :pct="spool.remaining_pct" :size="52" :stroke="6" :cls="cls" />
      </div>
    </div>
  </component>
</template>
<style scoped>
.card { display: flex; gap: 14px; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 14px; color: var(--text); transition: border-color .15s, transform .15s; }
.card:hover { border-color: var(--edge); text-decoration: none; transform: translateY(-1px); }
.card.ams { box-shadow: inset 3px 0 0 var(--edge); }
.card.selectable { cursor: pointer; position: relative; user-select: none; }
.card.selected { border-color: var(--edge); box-shadow: 0 0 0 2px var(--edge) inset; }
.tick { position: absolute; top: 10px; left: 10px; width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--line); background: var(--panel); display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 700; z-index: 1; }
.tick.on { background: var(--edge); border-color: var(--edge); color: var(--ink); }
.card.warn { border-color: rgba(243,197,107,.35); } .card.fail { border-color: rgba(255,107,94,.45); }
.img { width: 84px; height: 84px; flex: none; border-radius: 6px; overflow: hidden; background: #fff; display: flex; align-items: center; justify-content: center; }
.img img { width: 100%; height: 100%; object-fit: contain; }
.ph { width: 100%; height: 100%; display: block; }
.body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.name { font-weight: 600; font-size: 17px; display: flex; align-items: center; gap: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.meta { font-size: 14px; }
.specs { display: flex; gap: 10px; flex-wrap: wrap; font-size: 12px; }
.specs b { color: var(--text); font-weight: 600; }
.bottom { display: flex; align-items: center; gap: 12px; margin-top: auto; }
.nums { font-size: 14px; margin-top: 4px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
</style>
