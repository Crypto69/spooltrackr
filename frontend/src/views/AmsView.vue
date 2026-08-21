<script setup>
import { ref, computed } from 'vue'
import { useStore } from '../store'
import { api, fmtG, levelClass } from '../api'
import Gauge from '../components/Gauge.vue'
import SlotIdentify from '../components/SlotIdentify.vue'
import Modal from '../components/Modal.vue'

const store = useStore()
const identifying = ref(null)
const reassigning = ref(null)
const storedSpools = computed(() => store.spools.filter((s) => !s.location.startsWith('ams:')))

async function unassign(slot) {
  try { await api.post(`/api/ams/${slot.slot_index}/unassign`) } catch (e) { store.toast(e.message, 'error') }
}
async function assign(slot, id) {
  try { await api.post(`/api/ams/${slot.slot_index}/assign`, { spool_id: id }); reassigning.value = null } catch (e) { store.toast(e.message, 'error') }
}
// mock controls
const isMock = computed(() => store.printer.mode === 'mock')
async function mock(action, body = {}) {
  try { await api.post(`/api/debug/mock/${action}`, body) } catch (e) { store.toast(e.message, 'error') }
}
const mockPrint = () => mock('start', { name: `Test print ${new Date().toLocaleTimeString()}`, filaments: store.slots.filter((s) => s.present).slice(0, 2).map((s) => ({ type: s.tray_type, color: s.tray_color, used_g: 25 })) })
</script>
<template>
  <div class="page">
    <div class="page-head">
      <div><h1>AMS</h1><p>What is loaded in the printer right now. <span v-if="store.printer.connected" class="pass">● {{ store.printer.message }}</span><span v-else class="fail">● {{ store.printer.message }}</span></p></div>
      <div v-if="store.activePrint" class="badge edge">Printing: {{ store.activePrint.subtask_name }} · {{ store.activePrint.progress_pct }}%</div>
    </div>

    <div class="slots">
      <div v-for="slot in store.slots" :key="slot.slot_index" class="slot panel" :class="{ active: slot.active, empty: !slot.present, ask: slot.needs_identification }" :data-test="`slot-${slot.label}`">
        <div class="head"><span class="label num">{{ slot.label }}</span>
          <span v-if="slot.active" class="badge edge">Feeding</span>
          <span v-else-if="slot.needs_identification" class="badge warn">Identify</span>
          <span v-else-if="slot.present && slot.tray_uuid" class="badge pass">RFID</span>
          <span v-else-if="slot.present" class="badge">No RFID</span>
        </div>

        <div v-if="!slot.present" class="empty-slot muted">Empty</div>

        <template v-else>
          <div class="tray">
            <span class="swatch lg" :style="{ background: '#' + (slot.tray_color || '333') }"></span>
            <div><div class="t1">{{ slot.tray_sub_brands || slot.tray_type }}</div>
              <div class="muted small">AMS sees: {{ slot.tray_type }} · {{ slot.remain_pct != null && slot.remain_pct >= 0 ? slot.remain_pct + '%' : 'no estimate' }} · {{ slot.nozzle_temp_min }}–{{ slot.nozzle_temp_max }} °C</div></div>
          </div>

          <div v-if="slot.spool" class="spool">
            <router-link :to="`/spools/${slot.spool.id}`" class="sp-link">
              <img v-if="slot.spool.image_url" :src="slot.spool.image_url" alt="" />
              <span v-else class="swatch lg" :style="{ background: '#' + (slot.spool.colour_hex || '333') }"></span>
              <div class="grow"><div class="t1">{{ slot.spool.colour_name }}</div><div class="muted small">{{ slot.spool.subtype }} · {{ slot.spool.brand }} · #{{ slot.spool.id }}</div>
                <div class="num">{{ fmtG(slot.spool.remaining_g) }} <span class="muted">left</span> <span v-if="slot.spool.ams_divergent" class="badge warn">≠ AMS</span></div></div>
              <Gauge :pct="slot.spool.remaining_pct" :size="56" :stroke="6" :cls="levelClass(slot.spool.remaining_pct, store.thresholds)" />
            </router-link>
            <div class="row" style="margin-top:8px"><button class="sm ghost" @click="reassigning = slot">Change</button><button class="sm ghost" @click="unassign(slot)">Unlink</button></div>
          </div>
          <div v-else class="spool ask-box">
            <p>Not linked to a spool in your inventory yet.</p>
            <button class="primary" @click="identifying = slot" :data-test="`identify-${slot.label}`">Which spool is this?</button>
          </div>
        </template>
      </div>
    </div>

    <div v-if="isMock" class="panel mock">
      <h2>Mock printer controls <span class="muted" style="font-weight:400">(dev only — switch to live in Settings)</span></h2>
      <div class="row wrap">
        <button class="sm" @click="mock('load', { slot: 2, tray_uuid: 'C0FFEE00112233445566778899AABBCC', sub_brands: 'PLA Matte', colour: 'A3D8E1FF', remain: 91 })">Load PLA Matte Ice Blue → A3</button>
        <button class="sm" @click="mock('load', { slot: 2, tray_uuid: 'DEADBEEF00112233445566778899AABB', sub_brands: 'PETG HF', tray_type: 'PETG', colour: 'C41E3AFF', remain: 100 })">Load unknown PETG HF Red → A3</button>
        <button class="sm" @click="mock('unload', { slot: 2 })">Unload A3</button>
        <button class="sm" @click="mock('unload', { slot: 0 })">Unload A1</button>
        <button class="sm" @click="mockPrint()" :disabled="!!store.activePrint">Start print (25 g each)</button>
        <button class="sm" @click="mock('progress', { pct: 50 })" :disabled="!store.activePrint">Progress 50%</button>
        <button class="sm" @click="mock('finish')" :disabled="!store.activePrint">Finish</button>
        <button class="sm" @click="mock('fail')" :disabled="!store.activePrint">Fail</button>
      </div>
    </div>

    <SlotIdentify v-if="identifying" :slot="identifying" @close="identifying = null" />
    <Modal v-if="reassigning" :title="`Change spool in ${reassigning.label}`" @close="reassigning = null">
      <button v-for="s in storedSpools" :key="s.id" class="cand" @click="assign(reassigning, s.id)">
        <span class="swatch" :style="{ background: '#' + (s.colour_hex || '333') }"></span><span class="grow">{{ s.subtype }} · {{ s.colour_name }} <span class="muted">#{{ s.id }}</span></span><span class="num">{{ fmtG(s.remaining_g) }}</span>
      </button>
    </Modal>
  </div>
</template>
<style scoped>
.slots { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; margin-bottom: 20px; }
.slot { display: flex; flex-direction: column; gap: 12px; min-height: 220px; }
.slot.active { border-color: var(--edge); box-shadow: 0 0 0 1px var(--edge), 0 0 24px rgba(90,210,234,.15); }
.slot.ask { border-color: rgba(243,197,107,.5); }
.slot.empty { border-style: dashed; }
.head { display: flex; justify-content: space-between; align-items: center; }
.label { font-size: 23px; font-weight: 700; color: var(--edge); }
.empty-slot { flex: 1; display: flex; align-items: center; justify-content: center; font-size: 18px; }
.tray { display: flex; gap: 10px; align-items: center; }
.swatch.lg { width: 28px; height: 28px; }
.t1 { font-weight: 600; }
.small { font-size: 14px; }
.spool { border-top: 1px solid var(--line); padding-top: 12px; }
.sp-link { display: flex; gap: 10px; align-items: center; color: var(--text); }
.sp-link:hover { text-decoration: none; }
.sp-link img { width: 56px; height: 56px; border-radius: 6px; object-fit: contain; background: #fff; }
.ask-box p { color: var(--warn); margin-bottom: 8px; font-size: 15px; }
.cand { width: 100%; justify-content: flex-start; margin-bottom: 6px; font-weight: 500; }
.mock { border-style: dashed; }
</style>
