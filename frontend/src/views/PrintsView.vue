<script setup>
import { ref, watch } from 'vue'
import { useStore } from '../store'
import { api, fmtDate, fmtG } from '../api'
import Modal from '../components/Modal.vue'

const store = useStore()
const prints = ref([])
const resolving = ref(null)
const fraction = ref(50)
async function load() { prints.value = await api.get('/api/prints') }
load()
watch(() => [store.unresolvedPrints, store.activePrint?.progress_pct, store.activePrint?.id], load)

function openResolve(p) { resolving.value = p; fraction.value = p.progress_pct || 0 }
async function resolve(f) {
  try { await api.post(`/api/prints/${resolving.value.id}/resolve`, { fraction: f / 100 }); resolving.value = null; store.toast('Print resolved', 'success'); load(); store.refreshState() }
  catch (e) { store.toast(e.message, 'error') }
}
async function reassign(p, u, ev) {
  const id = ev.target.value ? Number(ev.target.value) : null
  try { await api.patch(`/api/prints/${p.id}/usage/${u.id}`, { spool_id: id }); load() } catch (e) { store.toast(e.message, 'error') }
}
async function remove(p) { if (!confirm('Delete this print record?')) return; await api.del(`/api/prints/${p.id}`); load(); store.refreshState() }
const statusCls = { running: 'edge', finished: 'pass', unresolved: 'warn', resolved: '', failed: 'fail' }
</script>
<template>
  <div class="page">
    <div class="page-head"><div><h1>Prints</h1><p>Filament use per job, read from the sliced file on the printer. Stopped prints wait for you to decide how much was used.</p></div></div>
    <div v-if="!prints.length" class="empty">No prints seen yet. Start a print on the X1C and it will appear here.</div>
    <div v-for="p in prints" :key="p.id" class="panel print" :data-test="`print-${p.id}`">
      <div class="head">
        <div><div class="name">{{ p.subtask_name }} <span class="badge" :class="statusCls[p.status]">{{ p.status }}<template v-if="p.status === 'running'"> · {{ p.progress_pct }}%</template></span></div>
          <div class="muted small">{{ fmtDate(p.started_at) }}<span v-if="p.ended_at"> → {{ fmtDate(p.ended_at) }}</span><span v-if="p.plate_index"> · plate {{ p.plate_index }}</span></div></div>
        <div class="row">
          <span class="num big">{{ p.planned_total_g != null ? fmtG(p.planned_total_g, 1) : '—' }}</span>
          <button v-if="p.status === 'unresolved'" class="primary sm" @click="openResolve(p)" :data-test="`resolve-${p.id}`">Resolve</button>
          <button class="ghost sm" @click="remove(p)">✕</button>
        </div>
      </div>
      <p v-if="!p.three_mf_fetched" class="warn small">Could not read filament usage from the printer{{ p.fetch_error ? ` (${p.fetch_error})` : '' }}. Adjust spools manually.</p>
      <table v-if="p.usage.length"><thead><tr><th>#</th><th>Sliced as</th><th>AMS</th><th>Spool</th><th class="right">Planned</th><th class="right">Applied</th></tr></thead><tbody>
        <tr v-for="u in p.usage" :key="u.id">
          <td class="num">{{ u.filament_index }}</td>
          <td><span class="swatch" :style="{ background: '#' + (u.colour_hex || '333') }"></span> {{ u.filament_type }}</td>
          <td class="num">{{ u.tray_index != null ? 'A' + (u.tray_index + 1) : '—' }}</td>
          <td>
            <router-link v-if="u.spool && u.applied_at" :to="`/spools/${u.spool.id}`">{{ u.spool.subtype }} {{ u.spool.colour_name }}</router-link>
            <select v-else :value="u.spool_id || ''" @change="reassign(p, u, $event)" style="width:auto"><option value="">— not linked —</option><option v-for="s in store.spools" :key="s.id" :value="s.id">{{ s.subtype }} {{ s.colour_name }} (#{{ s.id }})</option></select>
          </td>
          <td class="num right">{{ fmtG(u.planned_g, 1) }}</td>
          <td class="num right" :class="{ muted: u.applied_g == null }">{{ u.applied_g != null ? fmtG(u.applied_g, 1) : 'pending' }}</td>
        </tr></tbody></table>
    </div>

    <Modal v-if="resolving" :title="`How much of “${resolving.subtask_name}” printed?`" @close="resolving = null">
      <p class="muted">The print stopped at <b>{{ resolving.progress_pct }}%</b>. Planned total was {{ fmtG(resolving.planned_total_g, 1) }}. Choose how much to deduct.</p>
      <div class="field" style="margin-top:12px"><label>Deduct {{ fraction }}% = {{ fmtG((resolving.planned_total_g || 0) * fraction / 100, 1) }}</label><input type="range" min="0" max="100" v-model.number="fraction" /></div>
      <div class="actions"><button class="ghost" @click="resolve(0)">Nothing used</button><button @click="resolve(100)">Full amount</button><button class="primary" @click="resolve(fraction)" data-test="resolve-apply">Deduct {{ fraction }}%</button></div>
    </Modal>
  </div>
</template>
<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.name { font-weight: 600; font-size: 15px; display: flex; gap: 8px; align-items: center; }
.small { font-size: 12px; } .big { font-size: 18px; font-weight: 600; } .right { text-align: right; }
</style>
