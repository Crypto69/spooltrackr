<script setup>
import { ref, computed } from 'vue'
import { useStore } from '../store'
import { api } from '../api'
import SpoolCard from '../components/SpoolCard.vue'
import Modal from '../components/Modal.vue'
import SpoolForm from '../components/SpoolForm.vue'
import CompareTable from '../components/CompareTable.vue'

const store = useStore()
const q = ref('')
const material = ref('')
const location = ref('')
const lowOnly = ref(false)
const sort = ref('name')
const grouped = ref(false)
const adding = ref(false)
const comparing = ref(false)      // select mode on/off
const picked = ref([])            // spool ids, max 4
const showCompare = ref(false)
const MAX_COMPARE = 4
const pickedSpools = computed(() => picked.value.map((id) => store.spools.find((s) => s.id === id)).filter(Boolean))
function togglePick(id) {
  const i = picked.value.indexOf(id)
  if (i >= 0) picked.value.splice(i, 1)
  else if (picked.value.length < MAX_COMPARE) picked.value.push(id)
  else store.toast(`You can compare up to ${MAX_COMPARE} spools`, 'warn', 2500)
}
function stopComparing() { comparing.value = false; picked.value = []; showCompare.value = false }

const materials = computed(() => [...new Set(store.spools.map((s) => s.material))].sort())
const filtered = computed(() => {
  let list = store.spools.filter((s) => {
    if (material.value && s.material !== material.value) return false
    if (location.value === 'ams' && !s.location.startsWith('ams:')) return false
    if (location.value === 'stored' && s.location !== 'stored') return false
    if (location.value === 'sealed' && (s.opened || s.location !== 'stored')) return false
    if (lowOnly.value && !(s.remaining_g < store.thresholds.low_g || s.remaining_pct < store.thresholds.low_pct)) return false
    if (q.value) {
      const t = `${s.subtype} ${s.colour_name} ${s.brand} ${s.material} ${s.notes || ''}`.toLowerCase()
      if (!t.includes(q.value.toLowerCase())) return false
    }
    return true
  })
  const byNumDesc = (key) => (a, b) => {
    const av = a[key] ?? -Infinity, bv = b[key] ?? -Infinity
    return bv - av || a.subtype.localeCompare(b.subtype)
  }
  const by = {
    name: (a, b) => a.subtype.localeCompare(b.subtype) || a.colour_name.localeCompare(b.colour_name),
    remaining: (a, b) => a.remaining_pct - b.remaining_pct,
    location: (a, b) => a.location.localeCompare(b.location) || a.subtype.localeCompare(b.subtype),
    newest: (a, b) => new Date(b.created_at) - new Date(a.created_at),
    strength: byNumDesc('strength_mpa'),
    stiffness: byNumDesc('stiffness_mpa'),
    toughness: byNumDesc('toughness_kj_m2'),
    heat: byNumDesc('heat_resistance_c'),
    shrinkage: (a, b) => (a.shrinkage_rank ?? Infinity) - (b.shrinkage_rank ?? Infinity) || a.subtype.localeCompare(b.subtype),
  }
  return [...list].sort(by[sort.value])
})
const groups = computed(() => {
  if (!grouped.value || sort.value !== 'name') return [{ key: '', items: filtered.value }]
  const m = new Map()
  for (const s of filtered.value) { if (!m.has(s.subtype)) m.set(s.subtype, []); m.get(s.subtype).push(s) }
  return [...m.entries()].map(([key, items]) => ({ key, items }))
})
const totals = computed(() => ({
  count: store.spools.length,
  grams: store.spools.reduce((a, s) => a + s.remaining_g, 0),
  inAms: store.spools.filter((s) => s.location.startsWith('ams:')).length,
}))

async function create(data) {
  try { await api.post('/api/spools', data); adding.value = false; store.toast('Spool added', 'success') }
  catch (e) { store.toast(e.message, 'error') }
}
</script>
<template>
  <div class="page">
    <div class="page-head">
      <div><h1>My filament</h1>
        <p><span class="num">{{ totals.count }}</span> spools · <span class="num">{{ (totals.grams / 1000).toFixed(2) }} kg</span> estimated remaining · <span class="num">{{ totals.inAms }}</span> in the AMS
          <span v-if="store.lowCount" class="badge fail" style="margin-left:6px">{{ store.lowCount }} low</span></p></div>
      <button class="primary" @click="adding = true" data-test="add-spool">+ Add spool</button>
    </div>

    <div class="filters panel">
      <input v-model="q" placeholder="Search colour, type, brand…" class="grow" data-test="search" />
      <select v-model="material"><option value="">All materials</option><option v-for="m in materials" :key="m">{{ m }}</option></select>
      <select v-model="location"><option value="">Anywhere</option><option value="ams">In AMS</option><option value="stored">Stored</option><option value="sealed">Sealed / unopened</option></select>
      <select v-model="sort" data-test="sort"><option value="name">Sort: type</option><option value="remaining">Sort: least remaining</option><option value="location">Sort: location</option><option value="newest">Sort: newest</option><option value="strength">Sort: strength (bending)</option><option value="stiffness">Sort: stiffness (modulus)</option><option value="toughness">Sort: toughness (impact)</option><option value="heat">Sort: heat resistance</option><option value="shrinkage">Sort: least shrinkage</option></select>
      <label class="row" style="margin:0"><input type="checkbox" v-model="lowOnly" /> Low only</label>
      <label class="row" style="margin:0"><input type="checkbox" v-model="grouped" /> Group by type</label>
      <button :class="{ primary: comparing }" @click="comparing ? stopComparing() : (comparing = true)" data-test="compare-toggle">{{ comparing ? 'Done' : 'Compare' }}</button>
    </div>

    <div v-if="comparing" class="panel compare-bar" data-test="compare-bar">
      <span class="muted">Pick 2–{{ MAX_COMPARE }} spools to compare.</span>
      <span class="chips"><span v-for="s in pickedSpools" :key="s.id" class="badge edge">{{ s.subtype }} · {{ s.colour_name }}</span></span>
      <button class="primary" :disabled="pickedSpools.length < 2" @click="showCompare = true" data-test="compare-open">Compare {{ pickedSpools.length || '' }}</button>
    </div>

    <div v-if="!filtered.length" class="empty">No spools match.</div>
    <section v-for="g in groups" :key="g.key" class="group">
      <h2 v-if="g.key" class="micro">{{ g.key }} <span class="muted">· {{ g.items.length }}</span></h2>
      <div class="cards"><SpoolCard v-for="s in g.items" :key="s.id" :spool="s" :selectable="comparing" :selected="picked.includes(s.id)" @toggle="togglePick" /></div>
    </section>

    <Modal v-if="showCompare" title="Compare spools" wide @close="showCompare = false">
      <CompareTable :spools="pickedSpools" />
      <div class="actions"><button @click="showCompare = false">Close</button></div>
    </Modal>

    <Modal v-if="adding" title="Add a spool" @close="adding = false">
      <SpoolForm submit-label="Add spool" @submit="create" @cancel="adding = false" />
    </Modal>
  </div>
</template>
<style scoped>
.filters { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 20px; padding: 10px 12px; }
.filters select { width: auto; }
.compare-bar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: -10px 0 20px; padding: 10px 12px; border-color: var(--edge); }
.compare-bar .chips { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; }
.compare-bar button:disabled { opacity: .5; cursor: not-allowed; }
.group { margin-bottom: 22px; }
.group h2 { margin-bottom: 8px; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 12px; }
</style>
