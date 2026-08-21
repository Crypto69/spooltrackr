<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api'

const props = defineProps({ initial: Object, submitLabel: { type: String, default: 'Save' }, hideWeights: Boolean })
const emit = defineEmits(['submit', 'cancel'])

const products = ref([])
const form = ref({
  brand: 'Bambu Lab', material: 'PLA', subtype: '', colour_name: '', colour_hex: '', spool_type: 'spool',
  starting_weight_g: 1000, remaining_g: null, opened: false, notes: '', variant_id: null, product_id: null, image_url: null,
  ...(props.initial || {}),
})
const mode = ref(form.value.brand === 'Bambu Lab' ? 'bambu' : 'other')
const selProduct = ref(form.value.product_id || null)
const selVariant = ref(form.value.variant_id || null)

onMounted(async () => { products.value = await api.get('/api/catalog/products') })

const variants = computed(() => products.value.find((p) => p.id === selProduct.value)?.variants || [])

watch(selProduct, (id) => {
  const p = products.value.find((x) => x.id === id)
  if (p) { form.value.subtype = p.name; form.value.material = p.material; form.value.product_id = p.id; form.value.brand = 'Bambu Lab' }
  if (!variants.value.some((v) => v.id === selVariant.value)) selVariant.value = null
})
watch(selVariant, (id) => {
  const v = variants.value.find((x) => x.id === id)
  form.value.variant_id = v ? v.id : null
  if (v) { form.value.colour_name = v.colour_name; form.value.colour_hex = v.colour_hex || form.value.colour_hex; form.value.image_url = v.image_url }
})
watch(mode, (m) => { if (m === 'other') { form.value.variant_id = null; form.value.product_id = null; if (form.value.brand === 'Bambu Lab') form.value.brand = '' } })

function submit() {
  const out = { ...form.value }
  if (out.colour_hex) out.colour_hex = out.colour_hex.replace('#', '')
  if (!out.remaining_g) delete out.remaining_g
  emit('submit', out)
}
</script>
<template>
  <form @submit.prevent="submit" data-test="spool-form">
    <div class="field row">
      <label class="row"><input type="radio" value="bambu" v-model="mode" /> Bambu Lab (from catalog)</label>
      <label class="row"><input type="radio" value="other" v-model="mode" /> Other brand / custom</label>
    </div>
    <template v-if="mode === 'bambu'">
      <div class="grid2">
        <div class="field"><label>Product</label>
          <select v-model="selProduct" required><option :value="null" disabled>Select…</option><option v-for="p in products" :key="p.id" :value="p.id">{{ p.name }}</option></select></div>
        <div class="field"><label>Colour</label>
          <select v-model="selVariant"><option :value="null">Custom…</option><option v-for="v in variants" :key="v.id" :value="v.id">{{ v.colour_name }}{{ v.colour_code ? ` (${v.colour_code})` : '' }}</option></select></div>
      </div>
    </template>
    <div class="grid2" v-if="mode === 'other' || !selVariant">
      <div class="field" v-if="mode === 'other'"><label>Brand</label><input v-model="form.brand" required placeholder="eSUN, Polymaker…" /></div>
      <div class="field" v-if="mode === 'other'"><label>Material</label><input v-model="form.material" required placeholder="PLA, PETG…" /></div>
      <div class="field" v-if="mode === 'other'"><label>Type / line</label><input v-model="form.subtype" required placeholder="PLA+ , PETG Pro…" /></div>
      <div class="field"><label>Colour name</label><input v-model="form.colour_name" required /></div>
      <div class="field"><label>Colour hex</label><div class="row"><input v-model="form.colour_hex" placeholder="FF6600" maxlength="7" /><span class="swatch big" :style="{ background: '#' + (form.colour_hex || '').replace('#','') }"></span></div></div>
    </div>
    <div class="grid2" v-if="!hideWeights">
      <div class="field"><label>Spool type</label><select v-model="form.spool_type"><option value="spool">Filament with spool</option><option value="refill">Refill</option></select></div>
      <div class="field"><label>Filament weight (g)</label><input type="number" v-model.number="form.starting_weight_g" min="1" required /></div>
      <div class="field"><label>Remaining now (g) — blank = full</label><input type="number" v-model.number="form.remaining_g" min="0" /></div>
      <div class="field"><label>&nbsp;</label><label class="row"><input type="checkbox" v-model="form.opened" /> Opened</label></div>
    </div>
    <div class="field"><label>Notes</label><textarea v-model="form.notes" rows="2"></textarea></div>
    <div class="actions row" style="justify-content:flex-end">
      <button type="button" class="ghost" @click="emit('cancel')">Cancel</button>
      <button type="submit" class="primary">{{ submitLabel }}</button>
    </div>
  </form>
</template>
<style scoped>.swatch.big { width: 28px; height: 28px; border-radius: 6px; }</style>
