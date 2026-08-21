<script setup>
import { ref } from 'vue'
import { useStore } from '../store'
import { api, fmtDate } from '../api'

const store = useStore()
const s = ref(null)
const handlesText = ref('')
const saving = ref(false)
const showCode = ref(false)
async function load() { s.value = await api.get('/api/settings'); handlesText.value = (s.value.store_handles || []).join('\n') }
load()
async function save() {
  saving.value = true
  try {
    const body = { ...s.value, store_handles: handlesText.value.split(/\s+/).map((x) => x.trim()).filter(Boolean) }
    delete body.catalog_last_sync_at; delete body.catalog_last_sync_log
    s.value = await api.put('/api/settings', body); handlesText.value = s.value.store_handles.join('\n')
    store.toast('Settings saved', 'success'); setTimeout(() => store.refreshState(), 1500)
  } catch (e) { store.toast(e.message, 'error') } finally { saving.value = false }
}
async function reconnect() { try { const st = await api.post('/api/settings/reconnect'); store.printer = st; store.toast(st.message) } catch (e) { store.toast(e.message, 'error') } }
</script>
<template>
  <div class="page" v-if="s">
    <div class="page-head"><div><h1>Settings</h1></div></div>
    <form @submit.prevent="save">
      <div class="panel">
        <h2>Printer connection</h2>
        <div class="field"><label>Mode</label>
          <select v-model="s.printer_mode" data-test="printer-mode"><option value="live">Live — talk to my Bambu X1C</option><option value="mock">Mock — fake printer for testing</option><option value="off">Off</option></select></div>
        <div class="grid2">
          <div class="field"><label>Printer IP address or hostname</label><input v-model="s.printer_host" placeholder="192.168.1.50" /></div>
          <div class="field"><label>Serial number</label><input v-model="s.printer_serial" placeholder="00M09A3B0500123" class="num" /></div>
          <div class="field"><label>LAN access code</label><div class="row"><input v-model="s.printer_access_code" :type="showCode ? 'text' : 'password'" class="num" autocomplete="off" /><button type="button" class="sm" @click="showCode = !showCode">{{ showCode ? 'Hide' : 'Show' }}</button></div></div>
        </div>
        <details class="help"><summary>Where do I find these?</summary>
          <ol>
            <li>On the printer screen: <b>Settings (gear) → Network</b>. The <b>IP address</b> is shown there.</li>
            <li>Same screen: <b>Access Code</b> (8 characters). Tap the eye icon to reveal it.</li>
            <li><b>Serial number</b>: Settings → Device, or the sticker on the back of the printer (starts with 00M…).</li>
            <li>On X1 firmware 01.08 or newer, turn on <b>Developer Mode</b> (Settings → Network → Developer Mode / LAN Mode) so apps on your network are allowed to talk to the printer. You can stay bound to the Bambu cloud.</li>
            <li>Give the printer a fixed IP in your router so it does not change.</li>
          </ol>
        </details>
        <div class="row" style="margin-top:10px">
          <span class="led" :class="store.printer.connected ? 'on' : 'off'"></span><span>{{ store.printer.message }}</span>
          <span v-if="store.printer.nozzle_temp != null" class="muted num">nozzle {{ store.printer.nozzle_temp }} °C · bed {{ store.printer.bed_temp }} °C</span>
          <button type="button" class="sm" @click="reconnect">Reconnect</button>
        </div>
      </div>

      <div class="panel">
        <h2>Alerts</h2>
        <div class="grid2">
          <div class="field"><label>Low filament below (%)</label><input type="number" v-model.number="s.low_pct" min="0" max="100" /></div>
          <div class="field"><label>…or below (g)</label><input type="number" v-model.number="s.low_g" min="0" /></div>
          <div class="field"><label>Warn when AMS % and calculated % differ by more than</label><input type="number" v-model.number="s.divergence_pct" min="0" max="100" /></div>
        </div>
      </div>

      <div class="panel">
        <h2>Bambu store sync</h2>
        <div class="grid2">
          <div class="field"><label>Store region</label><select v-model="s.store_region"><option value="au">Australia (au)</option><option value="us">United States (us)</option><option value="eu">Europe (eu)</option><option value="uk">United Kingdom (uk)</option><option value="ca">Canada (ca)</option><option value="asia">Asia (asia)</option></select></div>
          <div class="field"><label>Last sync</label><div style="padding:7px 0">{{ s.catalog_last_sync_at ? fmtDate(s.catalog_last_sync_at) : 'never' }}</div></div>
        </div>
        <div class="field"><label>Product pages to read (one handle per line — the part after /products/ in the store URL). Pages found on the filament collection page are added automatically.</label>
          <textarea v-model="handlesText" rows="8" class="num"></textarea></div>
        <details v-if="s.catalog_last_sync_log"><summary class="micro" style="cursor:pointer">Last sync log</summary><pre class="log">{{ s.catalog_last_sync_log }}</pre></details>
      </div>

      <div class="row" style="justify-content:flex-end;margin-top:16px"><button type="submit" class="primary" :disabled="saving" data-test="save-settings">{{ saving ? 'Saving…' : 'Save settings' }}</button></div>
    </form>
  </div>
</template>
<style scoped>
.help { margin-top: 6px; font-size: 13px; color: var(--muted); } .help summary { cursor: pointer; color: var(--edge); } .help ol { padding-left: 20px; margin-top: 8px; display: grid; gap: 4px; }
.led { width: 10px; height: 10px; border-radius: 50%; background: var(--fail); } .led.on { background: var(--pass); }
.log { font-family: var(--font-data); font-size: 11px; white-space: pre-wrap; background: var(--ink); padding: 10px; border-radius: 6px; margin-top: 6px; max-height: 240px; overflow: auto; }
</style>
