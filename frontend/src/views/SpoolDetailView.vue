<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useStore } from '../store'
import { api, fmtDate, fmtG, locationLabel, levelClass } from '../api'
import Gauge from '../components/Gauge.vue'
import Modal from '../components/Modal.vue'
import SpoolForm from '../components/SpoolForm.vue'

const props = defineProps({ id: String })
const store = useStore()
const router = useRouter()
const spool = ref(null)
const err = ref('')
const modal = ref(null) // adjust | refill | edit
const adjust = ref({ remaining_g: null, delta_g: null, note: '' })
const refill = ref({ starting_weight_g: 1000, note: '' })

async function load() {
  try { spool.value = await api.get(`/api/spools/${props.id}`); adjust.value.remaining_g = spool.value.remaining_g } catch (e) { err.value = e.message }
}
load()
watch(() => store.spools.find((s) => s.id === Number(props.id))?.remaining_g, load)
watch(() => props.id, load)

const cls = computed(() => spool.value ? levelClass(spool.value.remaining_pct, store.thresholds) : '')
const specs = computed(() => {
  const p = spool.value?.product
  if (!p) return []
  const r = (a, b) => (a != null && b != null ? `${a}–${b}` : a ?? b ?? null)
  return [
    ['Nozzle temp', r(p.nozzle_temp_min_c, p.nozzle_temp_max_c), '°C'],
    ['Bed temp', r(p.bed_temp_min_c, p.bed_temp_max_c), '°C'],
    ['Heat resistance', p.heat_resistance_c, '°C'],
    ['Strength (bending)', p.strength_mpa, 'MPa'],
    ['Stiffness (modulus)', p.stiffness_mpa, 'MPa'],
    ['Toughness (impact)', p.toughness_kj_m2, 'kJ/m²'],
    ['Drying', p.drying_temp_c != null ? `${p.drying_temp_c} °C · ${p.drying_time_h ?? '?'} h` : null, ''],
    ['Density', p.density_g_cm3, 'g/cm³'],
  ].filter((x) => x[1] != null)
})
const metres = computed(() => {
  const d = spool.value?.product?.density_g_cm3
  if (!d || !spool.value) return null
  const area = Math.PI * Math.pow(0.175 / 2, 2) // 1.75 mm in cm
  return spool.value.remaining_g / d / area / 100
})

async function doAdjust(kind) {
  try {
    const body = kind === 'ams' ? { use_ams: true, note: 'Accepted AMS estimate' } : kind === 'set' ? { remaining_g: adjust.value.remaining_g, note: adjust.value.note } : { delta_g: adjust.value.delta_g, note: adjust.value.note }
    await api.post(`/api/spools/${props.id}/adjust`, body); modal.value = null; store.toast('Remaining weight updated', 'success'); load()
  } catch (e) { store.toast(e.message, 'error') }
}
async function doRefill(data) {
  try { await api.post(`/api/spools/${props.id}/refill`, { variant_id: data.variant_id, subtype: data.subtype, colour_name: data.colour_name, colour_hex: data.colour_hex, starting_weight_g: data.starting_weight_g || refill.value.starting_weight_g, note: data.notes }); modal.value = null; store.toast('Spool refilled', 'success'); load() }
  catch (e) { store.toast(e.message, 'error') }
}
async function doEdit(data) {
  try { delete data.remaining_g; await api.patch(`/api/spools/${props.id}`, data); modal.value = null; store.toast('Saved', 'success'); load() }
  catch (e) { store.toast(e.message, 'error') }
}
async function discard() {
  if (!confirm('Mark this spool as finished / thrown away? It stays in history.')) return
  await api.post(`/api/spools/${props.id}/discard`); router.push('/')
}
async function remove() {
  if (!confirm('Delete this spool and all its history? This cannot be undone.')) return
  await api.del(`/api/spools/${props.id}`); router.push('/')
}
const evLabel = { created: 'Added', loaded: 'Loaded', unloaded: 'Removed', print_usage: 'Print', manual_adjustment: 'Adjusted', ams_reconciliation: 'Synced to AMS', refill: 'Refilled', discarded: 'Discarded' }
</script>
<template>
  <div class="page" v-if="spool">
    <p class="micro" style="margin-bottom:10px"><router-link to="/">← Inventory</router-link></p>
    <div class="hero panel">
      <div class="img"><img v-if="spool.image_url" :src="spool.image_url" :alt="spool.colour_name" /><span v-else class="ph" :style="{ background: '#' + (spool.colour_hex || '333') }"></span></div>
      <div class="info">
        <div class="micro">{{ spool.brand }} · {{ spool.subtype }} · {{ spool.spool_type === 'refill' ? 'Refill' : 'Spool' }} · #{{ spool.id }}</div>
        <h1><span class="swatch lg" :style="{ background: '#' + (spool.colour_hex || '333') }"></span>{{ spool.colour_name }}
          <span v-if="spool.variant?.colour_code" class="muted num" style="font-size:14px">{{ spool.variant.colour_code }}</span></h1>
        <div class="row wrap" style="margin:8px 0">
          <span class="badge" :class="spool.location.startsWith('ams:') ? 'edge' : ''">{{ locationLabel(spool.location) }}</span>
          <span class="badge" v-if="!spool.opened">Sealed</span>
          <span class="badge pass" v-if="spool.tray_uuid" :title="spool.tray_uuid">RFID linked</span>
          <span class="badge warn" v-if="spool.ams_divergent">AMS says {{ spool.ams_remaining_pct }}%</span>
          <span class="badge fail" v-if="cls === 'fail'">Nearly empty</span><span class="badge warn" v-else-if="cls === 'warn'">Low</span>
        </div>
        <div class="kv">
          <div><span class="micro">Remaining</span><div class="big num">{{ fmtG(spool.remaining_g, 1) }}</div><div class="muted">of {{ fmtG(spool.starting_weight_g) }} · {{ spool.remaining_pct }}%<span v-if="metres"> · ≈ {{ metres.toFixed(0) }} m</span></div></div>
          <div><span class="micro">AMS estimate</span><div class="big num">{{ spool.ams_remaining_pct != null ? spool.ams_remaining_pct + '%' : '—' }}</div><div class="muted">{{ spool.last_seen_at ? 'seen ' + fmtDate(spool.last_seen_at) : 'never seen by AMS' }}</div></div>
          <div><span class="micro">Used</span><div class="big num">{{ fmtG(spool.total_used_g) }}</div><div class="muted">across {{ spool.prints.length }} print{{ spool.prints.length === 1 ? '' : 's' }}</div></div>
        </div>
        <div class="row wrap" style="margin-top:14px">
          <button class="primary" @click="modal = 'adjust'" data-test="adjust">Adjust weight</button>
          <button v-if="spool.ams_divergent" @click="doAdjust('ams')">Use AMS {{ spool.ams_remaining_pct }}%</button>
          <button @click="modal = 'refill'">Refill</button>
          <button @click="modal = 'edit'">Edit</button>
          <button class="ghost" @click="discard">Finished / discard</button>
          <button class="ghost danger" @click="remove">Delete</button>
        </div>
      </div>
      <Gauge :pct="spool.remaining_pct" :size="120" :stroke="10" :cls="cls" />
    </div>

    <div class="cols">
      <div class="panel">
        <h2>Properties <a v-if="spool.product?.store_url" :href="spool.product.store_url" target="_blank" rel="noopener" class="micro" style="float:right">Bambu store ↗</a></h2>
        <table v-if="specs.length"><tbody><tr v-for="[k, v, u] in specs" :key="k"><td class="muted">{{ k }}</td><td class="num" style="text-align:right">{{ v }} <span class="muted">{{ u }}</span></td></tr></tbody></table>
        <p v-else class="muted">No spec sheet linked. Edit the spool and pick a catalog product, or add specs in Catalog.</p>
        <p v-if="spool.variant?.store_price" class="muted" style="margin-top:10px">Store price: <span class="num">{{ spool.variant.store_currency }} {{ spool.variant.store_price }}</span> <span v-if="spool.variant.in_stock === false" class="fail">(out of stock)</span></p>
        <p v-if="spool.notes" style="margin-top:10px;white-space:pre-wrap">{{ spool.notes }}</p>
        <dl class="meta">
          <dt>Added</dt><dd>{{ fmtDate(spool.created_at) }}</dd>
          <dt>Opened</dt><dd>{{ spool.opened ? fmtDate(spool.opened_at) : 'Not yet' }}</dd>
          <dt>RFID</dt><dd class="num">{{ spool.tray_uuid || '—' }}</dd>
        </dl>
      </div>
      <div class="panel">
        <h2>History</h2>
        <table class="hist"><tbody>
          <tr v-for="e in spool.events" :key="e.id">
            <td class="muted nowrap">{{ fmtDate(e.created_at) }}</td>
            <td><span class="badge" :class="{ edge: e.type === 'print_usage', pass: e.type === 'refill', warn: e.type === 'manual_adjustment' || e.type === 'ams_reconciliation' }">{{ evLabel[e.type] || e.type }}</span> <span class="muted">{{ e.note }}</span></td>
            <td class="num right" :class="{ fail: e.delta_g < 0, pass: e.delta_g > 0 }">{{ e.delta_g != null && e.type !== 'created' ? (e.delta_g > 0 ? '+' : '') + e.delta_g.toFixed(1) + ' g' : '' }}</td>
            <td class="num right muted">{{ e.remaining_g != null ? e.remaining_g.toFixed(0) + ' g' : '' }}</td>
          </tr>
        </tbody></table>
      </div>
    </div>

    <Modal v-if="modal === 'adjust'" title="Adjust remaining weight" @close="modal = null">
      <p class="muted" style="margin-bottom:12px">Weigh the spool, subtract the empty spool (~250 g for a Bambu spool, ~0 for a refill on a reusable spool), and enter the filament weight.</p>
      <div class="field"><label>Set remaining filament (g)</label><div class="row"><input type="number" v-model.number="adjust.remaining_g" step="0.1" data-test="adjust-remaining" /><button class="primary" @click="doAdjust('set')" data-test="adjust-save">Set</button></div></div>
      <div class="field"><label>…or add / subtract (g)</label><div class="row"><input type="number" v-model.number="adjust.delta_g" step="0.1" placeholder="-12.5" /><button @click="doAdjust('delta')" :disabled="!adjust.delta_g">Apply</button></div></div>
      <div class="field"><label>Note</label><input v-model="adjust.note" placeholder="Weighed on kitchen scale" /></div>
      <div v-if="spool.ams_remaining_pct != null" class="field"><button @click="doAdjust('ams')">Use AMS estimate ({{ spool.ams_remaining_pct }}% = {{ fmtG(spool.starting_weight_g * spool.ams_remaining_pct / 100) }})</button></div>
    </Modal>
    <Modal v-if="modal === 'refill'" title="Refill this spool" @close="modal = null">
      <p class="muted" style="margin-bottom:12px">Same physical spool (and RFID tag, if any), new filament on it. History is kept.</p>
      <SpoolForm :initial="{ brand: spool.brand, material: spool.material, subtype: spool.subtype, colour_name: '', colour_hex: '', product_id: spool.product_id, starting_weight_g: 1000, spool_type: spool.spool_type, opened: true }" submit-label="Refill" @submit="doRefill" @cancel="modal = null" />
    </Modal>
    <Modal v-if="modal === 'edit'" title="Edit spool" @close="modal = null">
      <SpoolForm :initial="{ ...spool, colour_hex: spool.colour_hex || '' }" submit-label="Save" @submit="doEdit" @cancel="modal = null" />
    </Modal>
  </div>
  <div v-else class="page empty">{{ err || 'Loading…' }}</div>
</template>
<style scoped>
.hero { display: flex; gap: 22px; align-items: center; }
.img { width: 150px; height: 150px; border-radius: 10px; overflow: hidden; background: #fff; flex: none; }
.img img { width: 100%; height: 100%; object-fit: contain; } .ph { display: block; width: 100%; height: 100%; }
.info { flex: 1; min-width: 0; }
h1 { font-size: 26px; display: flex; align-items: center; gap: 10px; margin-top: 4px; }
.swatch.lg { width: 22px; height: 22px; }
.kv { display: flex; gap: 36px; flex-wrap: wrap; margin-top: 8px; }
.big { font-size: 24px; font-weight: 600; }
.cols { display: grid; grid-template-columns: 1fr 1.3fr; gap: 16px; margin-top: 16px; }
.meta { display: grid; grid-template-columns: auto 1fr; gap: 4px 14px; margin-top: 14px; font-size: 12px; }
.meta dt { color: var(--muted); }
.nowrap { white-space: nowrap; } .right { text-align: right; }
.hist td { padding: 6px 8px; font-size: 12.5px; }
@media (max-width: 860px) { .hero { flex-direction: column; align-items: flex-start; } .cols { grid-template-columns: 1fr; } }
</style>
