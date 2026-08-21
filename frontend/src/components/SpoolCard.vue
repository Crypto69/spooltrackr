<script setup>
import { computed } from 'vue'
import { useStore } from '../store'
import { fmtG, locationLabel, levelClass } from '../api'
import Gauge from './Gauge.vue'

const props = defineProps({ spool: { type: Object, required: true }, compact: Boolean })
const store = useStore()
const cls = computed(() => levelClass(props.spool.remaining_pct, store.thresholds))
const inAms = computed(() => props.spool.location?.startsWith('ams:'))
</script>
<template>
  <router-link :to="`/spools/${spool.id}`" class="card" :class="[cls, { ams: inAms }]" :data-test="`spool-${spool.id}`">
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
  </router-link>
</template>
<style scoped>
.card { display: flex; gap: 14px; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); padding: 14px; color: var(--text); transition: border-color .15s, transform .15s; }
.card:hover { border-color: var(--edge); text-decoration: none; transform: translateY(-1px); }
.card.ams { box-shadow: inset 3px 0 0 var(--edge); }
.card.warn { border-color: rgba(243,197,107,.35); } .card.fail { border-color: rgba(255,107,94,.45); }
.img { width: 84px; height: 84px; flex: none; border-radius: 6px; overflow: hidden; background: #fff; display: flex; align-items: center; justify-content: center; }
.img img { width: 100%; height: 100%; object-fit: contain; }
.ph { width: 100%; height: 100%; display: block; }
.body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.name { font-weight: 600; font-size: 15px; display: flex; align-items: center; gap: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.meta { font-size: 12px; }
.bottom { display: flex; align-items: center; gap: 12px; margin-top: auto; }
.nums { font-size: 12px; margin-top: 4px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
</style>
