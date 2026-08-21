<script setup>
import { ref, onMounted } from 'vue'
import { api, fmtG } from '../api'
import { useStore } from '../store'
import Modal from './Modal.vue'
import SpoolForm from './SpoolForm.vue'

const props = defineProps({ slot: { type: Object, required: true } })
const emit = defineEmits(['close'])
const store = useStore()
const cands = ref({ best: [], others: [] })
const creating = ref(false)
const busy = ref(false)

onMounted(async () => { cands.value = await api.get(`/api/ams/${props.slot.slot_index}/candidates`) })

async function pick(id) {
  busy.value = true
  try { await api.post(`/api/ams/${props.slot.slot_index}/assign`, { spool_id: id }); store.toast(`Slot ${props.slot.label} identified`, 'success'); emit('close') }
  catch (e) { store.toast(e.message, 'error') } finally { busy.value = false }
}
async function create(data) {
  busy.value = true
  try { await api.post(`/api/ams/${props.slot.slot_index}/assign`, { create: data }); store.toast(`New spool created in ${props.slot.label}`, 'success'); emit('close') }
  catch (e) { store.toast(e.message, 'error') } finally { busy.value = false }
}
const initial = () => ({
  brand: props.slot.tray_uuid ? 'Bambu Lab' : '', material: props.slot.tray_type || '', subtype: props.slot.tray_sub_brands || props.slot.tray_type || '',
  colour_name: '', colour_hex: props.slot.tray_color || '', starting_weight_g: props.slot.tray_weight || 1000, opened: true,
})
</script>
<template>
  <Modal :title="`Which spool is in ${slot.label}?`" @close="emit('close')">
    <p class="muted" style="margin-bottom:12px">
      The AMS sees <b>{{ slot.tray_sub_brands || slot.tray_type || 'a tray' }}</b>
      <span class="swatch" :style="{ background: '#' + (slot.tray_color || '333') }"></span>
      <span v-if="slot.tray_uuid">with Bambu RFID tag <span class="num">{{ slot.tray_uuid.slice(0, 8) }}…</span>. Picking a spool below links that tag to it for good.</span>
      <span v-else>with no RFID tag (third-party).</span>
    </p>
    <template v-if="!creating">
      <div v-if="cands.best.length" class="micro" style="margin-bottom:6px">Best matches</div>
      <button v-for="s in cands.best" :key="s.id" class="cand" :disabled="busy" @click="pick(s.id)" :data-test="`cand-${s.id}`">
        <span class="swatch" :style="{ background: '#' + (s.colour_hex || '333') }"></span>
        <span class="grow">{{ s.subtype }} · {{ s.colour_name }} <span class="muted">#{{ s.id }}</span></span>
        <span class="num">{{ fmtG(s.remaining_g) }}</span>
      </button>
      <details v-if="cands.others.length" style="margin-top:10px">
        <summary class="micro" style="cursor:pointer">Other stored spools ({{ cands.others.length }})</summary>
        <button v-for="s in cands.others" :key="s.id" class="cand" :disabled="busy" @click="pick(s.id)">
          <span class="swatch" :style="{ background: '#' + (s.colour_hex || '333') }"></span>
          <span class="grow">{{ s.subtype }} · {{ s.colour_name }} <span class="muted">#{{ s.id }}</span></span>
          <span class="num">{{ fmtG(s.remaining_g) }}</span>
        </button>
      </details>
      <div class="actions">
        <button class="ghost" @click="emit('close')">Later</button>
        <button class="primary" @click="creating = true" data-test="create-new">Create new spool</button>
      </div>
    </template>
    <SpoolForm v-else :initial="initial()" submit-label="Create & assign" @submit="create" @cancel="creating = false" />
  </Modal>
</template>
<style scoped>
.cand { width: 100%; justify-content: flex-start; margin-bottom: 6px; text-align: left; font-weight: 500; }
</style>
