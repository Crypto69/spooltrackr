<script setup>
import { onMounted } from 'vue'
import { useStore } from './store'

const store = useStore()
onMounted(() => store.init())

const nav = [
  { to: '/', label: 'Inventory' },
  { to: '/ams', label: 'AMS' },
  { to: '/prints', label: 'Prints' },
  { to: '/catalog', label: 'Catalog' },
  { to: '/settings', label: 'Settings' },
]
</script>

<template>
  <header class="top">
    <router-link to="/" class="brand">
      <svg viewBox="0 0 100 100" width="26" height="26" aria-hidden="true"><circle cx="50" cy="50" r="42" fill="none" stroke="#5ad2ea" stroke-width="14"/><circle cx="50" cy="50" r="12" fill="#5ad2ea"/></svg>
      <span>SpoolTrackr</span>
    </router-link>
    <nav>
      <router-link v-for="n in nav" :key="n.to" :to="n.to" class="navlink">
        {{ n.label }}
        <span v-if="n.to === '/ams' && store.needsIdentification.length" class="dot warn" :title="`${store.needsIdentification.length} slot(s) need identifying`"></span>
        <span v-else-if="n.to === '/prints' && store.unresolvedPrints" class="dot warn" :title="`${store.unresolvedPrints} unresolved print(s)`"></span>
        <span v-else-if="n.to === '/' && store.lowCount" class="dot fail" :title="`${store.lowCount} low spool(s)`"></span>
      </router-link>
    </nav>
    <div class="status" data-test="printer-status">
      <span class="led" :class="store.printer.connected ? 'on' : 'off'"></span>
      <span class="micro">{{ store.printer.mode }}</span>
      <span class="muted small">{{ store.printer.message }}</span>
      <span v-if="store.activePrint" class="badge edge">Printing {{ store.activePrint.progress_pct }}%</span>
    </div>
  </header>

  <main>
    <router-view v-if="store.loaded" />
    <div v-else class="empty">Loading…</div>
  </main>

  <div class="toasts" aria-live="polite">
    <div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.kind">{{ t.text }}</div>
  </div>

  <footer class="foot micro" v-if="store.version">spooltrackr · {{ store.version.sha }} · {{ store.version.built }}</footer>
</template>

<style scoped>
.top { position: sticky; top: 0; z-index: 20; display: flex; align-items: center; gap: 24px; padding: 0 20px; height: 54px; background: rgba(20,23,28,.92); backdrop-filter: blur(8px); border-bottom: 1px solid var(--line); }
.brand { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 16px; color: var(--text); letter-spacing: -0.01em; }
.brand:hover { text-decoration: none; }
nav { display: flex; gap: 4px; flex: 1; }
.navlink { position: relative; color: var(--muted); padding: 6px 12px; border-radius: 6px; font-weight: 600; font-size: 13px; }
.navlink:hover { color: var(--text); text-decoration: none; background: var(--panel-2); }
.navlink.router-link-exact-active, .navlink.router-link-active:not([href='/']) { color: var(--edge); background: rgba(90,210,234,.08); }
.dot { position: absolute; top: 6px; right: 6px; width: 7px; height: 7px; border-radius: 50%; }
.dot.warn { background: var(--warn); } .dot.fail { background: var(--fail); }
.status { display: flex; align-items: center; gap: 8px; }
.small { font-size: 12px; }
.led { width: 9px; height: 9px; border-radius: 50%; background: var(--fail); box-shadow: 0 0 8px var(--fail); }
.led.on { background: var(--pass); box-shadow: 0 0 8px var(--pass); }
.foot { text-align: center; padding: 20px; }
@media (max-width: 720px) { .top { gap: 10px; padding: 0 10px; overflow-x: auto; } .status .small { display: none; } }
</style>
