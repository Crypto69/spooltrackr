<script setup>
import { ref, computed } from 'vue'
import { useStore } from '../store'
import { api, fmtDate } from '../api'
import Modal from '../components/Modal.vue'

const store = useStore()
const products = ref([])
const settings = ref(null)
const syncing = ref(false)
const open = ref(null)
const editing = ref(null)
const q = ref('')
const SPEC = [
  ['nozzle_temp_min_c', 'Nozzle min °C'], ['nozzle_temp_max_c', 'Nozzle max °C'], ['bed_temp_min_c', 'Bed min °C'], ['bed_temp_max_c', 'Bed max °C'],
  ['heat_resistance_c', 'Heat resistance °C'], ['strength_mpa', 'Strength MPa'], ['stiffness_mpa', 'Stiffness MPa'], ['toughness_kj_m2', 'Toughness kJ/m²'],
  ['drying_temp_c', 'Drying °C'], ['drying_time_h', 'Drying h'], ['density_g_cm3', 'Density g/cm³'],
]
async function load() { [products.value, settings.value] = await Promise.all([api.get('/api/catalog/products'), api.get('/api/settings')]) }
load()
const filtered = computed(() => products.value.filter((p) => !q.value || `${p.name} ${p.material} ${p.variants.map((v) => v.colour_name).join(' ')}`.toLowerCase().includes(q.value.toLowerCase())))
const ownedBy = computed(() => { const m = {}; for (const s of store.spools) { m[s.variant_id] = (m[s.variant_id] || 0) + 1 }; return m })

async function sync() {
  syncing.value = true
  try { const r = await api.post('/api/catalog/sync'); store.toast(`Synced ${r.products} products: ${r.variants_new} new colours, ${r.variants_updated} updated, ${r.spools_linked} spools linked`, 'success', 8000); await load(); store.refreshSpools() }
  catch (e) { store.toast('Sync failed: ' + e.message, 'error') } finally { syncing.value = false }
}
async function saveSpec() {
  const body = {}; for (const [k] of SPEC) body[k] = editing.value[k] === '' ? null : editing.value[k]
  body.name = editing.value.name; body.material = editing.value.material; body.store_handle = editing.value.store_handle || null
  try { if (editing.value.id) await api.patch(`/api/catalog/products/${editing.value.id}`, body); else await api.post('/api/catalog/products', body); editing.value = null; load() } catch (e) { store.toast(e.message, 'error') }
}
async function setHex(v, ev) { try { await api.patch(`/api/catalog/variants/${v.id}`, { colour_hex: ev.target.value }); v.colour_hex = ev.target.value.replace('#', '').toUpperCase() } catch (e) { store.toast(e.message, 'error') } }
</script>
<template>
  <div class="page">
    <div class="page-head">
      <div><h1>Catalog</h1><p>Bambu product lines, their spec sheets, and every colour on the store. <span v-if="settings?.catalog_last_sync_at">Last store sync {{ fmtDate(settings.catalog_last_sync_at) }}.</span><span v-else>Never synced with the store yet.</span></p></div>
      <div class="row"><button @click="editing = { name: '', material: 'PLA' }">+ Product</button><button class="primary" @click="sync" :disabled="syncing" data-test="sync">{{ syncing ? 'Syncing…' : 'Sync from Bambu store' }}</button></div>
    </div>
    <input v-model="q" placeholder="Search products or colours…" style="margin-bottom:14px" />
    <div v-for="p in filtered" :key="p.id" class="panel prod">
      <div class="head" @click="open = open === p.id ? null : p.id">
        <div><span class="micro">{{ p.material }}</span><div class="name">{{ p.name }} <span class="muted">· {{ p.variants.length }} colours</span></div></div>
        <div class="row">
          <span class="muted small">{{ p.nozzle_temp_min_c }}–{{ p.nozzle_temp_max_c }} °C · bed {{ p.bed_temp_min_c }}–{{ p.bed_temp_max_c }} °C<template v-if="p.strength_mpa"> · {{ p.strength_mpa }} MPa</template></span>
          <a v-if="p.store_url" :href="p.store_url" target="_blank" rel="noopener" class="btn sm" @click.stop>Store ↗</a>
          <button class="sm" @click.stop="editing = { ...p }">Specs</button>
          <span class="chev">{{ open === p.id ? '▾' : '▸' }}</span>
        </div>
      </div>
      <div v-if="open === p.id" class="variants">
        <div v-for="v in p.variants" :key="v.id" class="var" :class="{ owned: ownedBy[v.id] }">
          <img v-if="v.image_url" :src="v.image_url" :alt="v.colour_name" loading="lazy" />
          <span v-else class="ph" :style="{ background: '#' + (v.colour_hex || '333') }"></span>
          <div class="vname">{{ v.colour_name }}</div>
          <div class="muted small num">{{ v.colour_code || '' }} <span v-if="v.store_price">· {{ v.store_currency }} {{ v.store_price }}</span></div>
          <div class="row small"><input type="color" :value="'#' + (v.colour_hex || '333333')" @change="setHex(v, $event)" title="Colour used to match AMS reports" /><span v-if="ownedBy[v.id]" class="badge edge">Own {{ ownedBy[v.id] }}</span><span v-else-if="v.in_stock === false" class="badge fail">Sold out</span></div>
        </div>
        <p v-if="!p.variants.length" class="muted">No colours yet — sync from the store or set a store handle in Specs.</p>
      </div>
    </div>

    <Modal v-if="editing" :title="editing.id ? `Specs: ${editing.name}` : 'New product line'" @close="editing = null">
      <div class="grid2">
        <div class="field"><label>Name</label><input v-model="editing.name" /></div>
        <div class="field"><label>Material</label><input v-model="editing.material" /></div>
        <div class="field" style="grid-column:1/-1"><label>Store handle (the bit after /products/ on the Bambu store)</label><input v-model="editing.store_handle" placeholder="pla-basic-filament" /></div>
        <div v-for="[k, label] in SPEC" :key="k" class="field"><label>{{ label }}</label><input type="number" step="any" v-model.number="editing[k]" /></div>
      </div>
      <div class="actions"><button class="ghost" @click="editing = null">Cancel</button><button class="primary" @click="saveSpec">Save</button></div>
    </Modal>
  </div>
</template>
<style scoped>
.prod { padding: 12px 16px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; cursor: pointer; flex-wrap: wrap; }
.name { font-weight: 600; font-size: 17px; }
.small { font-size: 14px; } .chev { color: var(--muted); }
.variants { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; margin-top: 14px; }
.var { background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 8px; display: flex; flex-direction: column; gap: 4px; }
.var.owned { border-color: rgba(90,210,234,.5); }
.var img, .var .ph { width: 100%; aspect-ratio: 1; object-fit: contain; border-radius: 6px; background: #fff; display: block; }
.vname { font-weight: 600; font-size: 15px; }
input[type=color] { width: 28px; height: 22px; padding: 0; border: none; background: none; }
</style>
