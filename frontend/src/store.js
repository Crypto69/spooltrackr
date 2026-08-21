import { defineStore } from 'pinia'
import { api } from './api'

export const useStore = defineStore('main', {
  state: () => ({
    spools: [],
    slots: [],
    printer: { connected: false, mode: 'off', message: '' },
    activePrint: null,
    lowCount: 0,
    unresolvedPrints: 0,
    thresholds: { low_pct: 20, low_g: 150 },
    toasts: [],
    loaded: false,
    sse: null,
    version: null,
  }),
  getters: {
    spoolById: (s) => (id) => s.spools.find((x) => x.id === id),
    lowSpools: (s) => s.spools.filter((x) => x.remaining_g < s.thresholds.low_g || x.remaining_pct < s.thresholds.low_pct),
    needsIdentification: (s) => s.slots.filter((x) => x.needs_identification),
  },
  actions: {
    async init() {
      await Promise.all([this.refreshState(), this.refreshSpools()])
      this.loaded = true
      api.get('/api/version').then((v) => (this.version = v)).catch(() => {})
      this.connect()
    },
    async refreshState() {
      const st = await api.get('/api/state')
      this.slots = st.slots
      this.printer = st.printer
      this.activePrint = st.active_print
      this.lowCount = st.low_count
      this.unresolvedPrints = st.unresolved_prints
      this.thresholds = st.thresholds
    },
    async refreshSpools() {
      this.spools = await api.get('/api/spools')
    },
    async refreshSpool(id) {
      try {
        const s = await api.get(`/api/spools/${id}`)
        const i = this.spools.findIndex((x) => x.id === id)
        if (s.location === 'discarded') {
          if (i >= 0) this.spools.splice(i, 1)
        } else if (i >= 0) this.spools[i] = { ...this.spools[i], ...s }
        else this.spools.push(s)
      } catch {
        this.spools = this.spools.filter((x) => x.id !== id)
      }
    },
    connect() {
      if (this.sse) this.sse.close()
      const es = new EventSource('/api/events')
      this.sse = es
      es.addEventListener('ams', (e) => { this.slots = JSON.parse(e.data) })
      es.addEventListener('spool', (e) => {
        const d = JSON.parse(e.data)
        if (d.deleted) this.spools = this.spools.filter((x) => x.id !== d.id)
        else this.refreshSpool(d.id)
        this.refreshState()
      })
      es.addEventListener('print', () => this.refreshState())
      es.addEventListener('printer', (e) => { this.printer = JSON.parse(e.data); })
      es.addEventListener('toast', (e) => { const d = JSON.parse(e.data); this.toast(d.text, d.kind) })
      es.onerror = () => { this.printer = { ...this.printer, message: 'Reconnecting to server…' } }
      es.onopen = () => this.refreshState()
    },
    toast(text, kind = 'info', ms = 5000) {
      const id = Date.now() + Math.random()
      this.toasts.push({ id, text, kind })
      setTimeout(() => { this.toasts = this.toasts.filter((t) => t.id !== id) }, ms)
    },
  },
})
