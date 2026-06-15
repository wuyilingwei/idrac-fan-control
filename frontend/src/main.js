// main.js — Vue 3 + vue-i18n 启动入口。
// Locale 解析: 优先 localStorage('lang'),否则跟随 navigator.language(zh-* → zh-CN,其余 → en)。

import { createApp } from 'vue'
import { createI18n } from 'vue-i18n'
import App from './App.vue'
import zhCN from './locales/zh-CN.json'
import en from './locales/en.json'

function detectLocale() {
  const stored = localStorage.getItem('lang')
  if (stored === 'zh-CN' || stored === 'en') return stored
  const nav = (navigator.language || 'en').toLowerCase()
  return nav.startsWith('zh') ? 'zh-CN' : 'en'
}

const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: 'en',
  messages: { 'zh-CN': zhCN, en },
})

createApp(App).use(i18n).mount('#app')
