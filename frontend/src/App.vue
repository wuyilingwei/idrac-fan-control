<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from './api.js'
import Login from './components/Login.vue'
import StatusView from './views/StatusView.vue'
import DevicesView from './views/DevicesView.vue'
import CurvesView from './views/CurvesView.vue'
import SettingsView from './views/SettingsView.vue'
import NotifiersView from './views/NotifiersView.vue'

const { t, locale } = useI18n()

const tabs = [
  { key: 'status', comp: StatusView },
  { key: 'devices', comp: DevicesView },
  { key: 'curves', comp: CurvesView },
  { key: 'settings', comp: SettingsView },
  { key: 'notifiers', comp: NotifiersView },
]

const active = ref('status')
const authReady = ref(false)
const loggedIn = ref(false)
const authRequired = ref(false)

async function checkAuth() {
  try {
    const s = await api.authStatus()
    authRequired.value = !!s.auth_required
    loggedIn.value = !authRequired.value || !!localStorage.getItem('auth_token')
  } catch {
    loggedIn.value = true
  } finally {
    authReady.value = true
  }
}

function onUnauthorized() {
  localStorage.removeItem('auth_token')
  loggedIn.value = false
}

function onLoggedIn() {
  loggedIn.value = true
}

async function logout() {
  try { await api.logout() } catch {}
  localStorage.removeItem('auth_token')
  loggedIn.value = false
}

function switchLang(l) {
  locale.value = l
  localStorage.setItem('lang', l)
}

onMounted(() => {
  checkAuth()
  window.addEventListener('idrac-unauthorized', onUnauthorized)
})
onUnmounted(() => {
  window.removeEventListener('idrac-unauthorized', onUnauthorized)
})
</script>

<template>
  <p v-if="!authReady" style="padding:24px;">{{ t('common.loading') }}</p>
  <Login v-else-if="!loggedIn" @logged-in="onLoggedIn" />
  <div v-else class="app">
    <header>
      <div class="brand">
        <img src="/logo.svg" class="brand-logo" alt="" />
        <h1>{{ t('app.title') }}</h1>
      </div>
      <div class="lang">
        <button :class="{ active: locale === 'zh-CN' }" @click="switchLang('zh-CN')">中</button>
        <button :class="{ active: locale === 'en' }" @click="switchLang('en')">EN</button>
        <button v-if="authRequired" @click="logout" style="margin-left:10px;">{{ t('login.logout') }}</button>
      </div>
    </header>
    <nav>
      <button
        v-for="tab in tabs"
        :key="tab.key"
        :class="{ active: active === tab.key }"
        @click="active = tab.key"
      >
        {{ t(`app.tabs.${tab.key}`) }}
      </button>
    </nav>
    <main>
      <component :is="tabs.find((t) => t.key === active).comp" />
    </main>
  </div>
</template>

<style>
/* === 工科面板风格 — 扁平 / 单色 / monospace 数字 / 清晰边界 === */
:root {
  --bg: #f2f3f5;
  --panel: #ffffff;
  --border: #d4d4d8;
  --border-strong: #a1a1aa;
  --text: #18181b;
  --text-dim: #71717a;
  --accent: #1f6feb;
  --accent-hover: #1858c4;
  --danger: #b91c1c;
  --warn: #b45309;
  --row-alt: #fafafa;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Helvetica Neue", sans-serif;
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.app { max-width: 1400px; margin: 0 auto; padding: 14px 18px 32px; }

/* === Header === */
header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 0 12px;
  border-bottom: 1px solid var(--border);
}
.brand { display: flex; align-items: center; gap: 10px; }
.brand-logo { width: 26px; height: 26px; display: block; flex: 0 0 26px; }
header h1 {
  margin: 0; font-size: 15px; font-weight: 600;
  letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--text);
}
.lang { display: flex; align-items: center; }
.lang button {
  margin-left: 4px; padding: 4px 10px;
  border: 1px solid var(--border); background: var(--panel);
  border-radius: 3px; cursor: pointer;
  font-size: 12px; color: var(--text);
}
.lang button:hover { border-color: var(--border-strong); }
.lang button.active { background: var(--accent); color: white; border-color: var(--accent); }

/* === Tabs === */
nav { display: flex; gap: 0; padding: 14px 0 0; flex-wrap: wrap; }
nav button {
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-right: none;
  background: var(--panel);
  cursor: pointer; font-size: 13px;
  color: var(--text-dim);
  border-radius: 0;
  letter-spacing: 0.02em;
  font-weight: 500;
}
nav button:first-child { border-top-left-radius: 4px; border-bottom-left-radius: 4px; }
nav button:last-child  { border-right: 1px solid var(--border); border-top-right-radius: 4px; border-bottom-right-radius: 4px; }
nav button:hover { background: var(--row-alt); color: var(--text); }
nav button.active {
  background: var(--accent); color: white; border-color: var(--accent);
}
nav button.active + button { border-left-color: var(--accent); }

/* === Main panel === */
main {
  background: var(--panel); padding: 18px 20px;
  border: 1px solid var(--border);
  border-top: none;
  border-radius: 0 4px 4px 4px;
}
main h2 {
  margin: 0 0 14px; font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
main h3 {
  margin: 14px 0 8px; font-size: 13px; font-weight: 600;
  color: var(--text);
}

/* === Buttons === */
button {
  padding: 5px 12px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text);
  cursor: pointer;
  font-size: 12.5px;
  border-radius: 3px;
  transition: border-color 0.12s, background 0.12s;
  margin-right: 4px;
}
button:hover { border-color: var(--border-strong); background: var(--row-alt); }
button.primary {
  background: var(--accent); color: white; border-color: var(--accent);
  padding: 6px 14px; font-weight: 500;
}
button.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
button.primary:disabled { opacity: 0.4; cursor: not-allowed; }
button.danger {
  background: var(--panel); color: var(--danger);
  border-color: var(--border);
  padding: 4px 10px;
}
button.danger:hover { background: #fef2f2; border-color: var(--danger); }

/* === Inputs === */
input, select, textarea {
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: 3px;
  font-size: 13px;
  background: var(--panel);
  color: var(--text);
  font-family: inherit;
  transition: border-color 0.12s;
}
input:focus, select:focus, textarea:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(31, 111, 235, 0.15);
}
input[type="number"] { font-family: var(--mono); width: 80px; }

/* === Table === */
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td {
  padding: 8px 10px; text-align: left;
  border-bottom: 1px solid var(--row-alt);
}
th {
  background: var(--row-alt);
  font-weight: 600; font-size: 11.5px;
  text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--text-dim);
  border-bottom: 1px solid var(--border);
}
tbody tr:hover { background: var(--row-alt); }
td:has(input[type="number"]) { font-family: var(--mono); }

/* === Misc === */
.error { color: var(--danger); margin: 8px 0; font-size: 13px; }
.warn { color: var(--warn); margin: 8px 0; font-size: 12.5px; padding: 6px 10px; background: #fefce8; border: 1px solid #fde68a; border-radius: 3px; }
.section { margin: 16px 0; }
.section > h3:first-child { margin-top: 0; }

/* === Form labels(p > label 块) === */
p label { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; }
p { margin: 8px 0; }
</style>
