import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import '@fontsource-variable/archivo'
import './style.css'
import App from './App.vue'
import InventoryView from './views/InventoryView.vue'
import AmsView from './views/AmsView.vue'
import SpoolDetailView from './views/SpoolDetailView.vue'
import PrintsView from './views/PrintsView.vue'
import CatalogView from './views/CatalogView.vue'
import SettingsView from './views/SettingsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'inventory', component: InventoryView },
    { path: '/ams', name: 'ams', component: AmsView },
    { path: '/spools/:id', name: 'spool', component: SpoolDetailView, props: true },
    { path: '/prints', name: 'prints', component: PrintsView },
    { path: '/catalog', name: 'catalog', component: CatalogView },
    { path: '/settings', name: 'settings', component: SettingsView },
  ],
})

createApp(App).use(createPinia()).use(router).mount('#app')
