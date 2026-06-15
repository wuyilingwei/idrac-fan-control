<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const { t, locale } = useI18n()
const settings = ref(null)
const error = ref('')
const msg = ref('')
const savedAt = ref('')

async function load() {
  try { settings.value = await api.getSettings(); error.value = '' }
  catch (e) { error.value = e.message }
}

async function save() {
  try {
    settings.value = await api.updateSettings(settings.value)
    msg.value = t('common.save') + ' ✓'
    const d = new Date()
    const pad = (n) => String(n).padStart(2, '0')
    savedAt.value = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
    setTimeout(() => { msg.value = ''; savedAt.value = '' }, 1500)
  } catch (e) { error.value = e.message }
}

function changeLang(l) {
  if (l === 'auto') localStorage.removeItem('lang')
  else { localStorage.setItem('lang', l); locale.value = l }
}

onMounted(load)
</script>

<template>
  <div v-if="settings">
    <h2>{{ t('settings.title') }}</h2>
    <div class="error" v-if="error">{{ error }}</div>
    <p v-if="msg" class="saved-msg">
      <span>{{ msg }}</span>
      <span class="saved-time">{{ savedAt }}</span>
    </p>

    <div class="form">
      <label class="row check">
        <input type="checkbox" v-model="settings.failsafe_enabled" />
        <span class="label-text">{{ t('settings.failsafe_enabled') }}</span>
      </label>

      <label class="row">
        <span class="label-text">{{ t('settings.failsafe_temp_c') }}</span>
        <input type="number" class="num" v-model.number="settings.failsafe_temp_c" />
      </label>

      <label class="row">
        <span class="label-text">{{ t('settings.poll_interval_s') }}</span>
        <input type="number" class="num" v-model.number="settings.poll_interval_s" />
      </label>

      <label class="row check">
        <input type="checkbox" v-model="settings.autostart" />
        <span class="label-text">{{ t('settings.autostart') }}</span>
      </label>

      <label class="row check">
        <input type="checkbox" v-model="settings.restore_on_exit" />
        <span class="label-text">{{ t('settings.restore_on_exit') }}</span>
      </label>

      <label class="row">
        <span class="label-text">{{ t('settings.language') }}</span>
        <select
          class="lang-select"
          :value="settings.language"
          @change="(e) => { settings.language = e.target.value; changeLang(e.target.value) }"
        >
          <option value="auto">{{ t('settings.lang_auto') }}</option>
          <option value="zh-CN">{{ t('settings.lang_zh') }}</option>
          <option value="en">{{ t('settings.lang_en') }}</option>
        </select>
      </label>
    </div>

    <h3 class="security-title">{{ t('settings.security_title') }}</h3>
    <p class="warn" v-if="!settings.master_password">{{ t('settings.no_pw_warn') }}</p>

    <div class="form">
      <label class="row">
        <span class="label-text">{{ t('settings.master_password') }}</span>
        <input type="password" class="pw" v-model="settings.master_password"
               :placeholder="t('settings.master_password_placeholder')" />
      </label>
      <label class="row">
        <span class="label-text">{{ t('settings.bind_host') }}</span>
        <input type="text" class="host" v-model="settings.bind_host"
               :disabled="!settings.master_password" />
      </label>
      <p class="hint">{{ t('settings.bind_host_hint') }}</p>
    </div>

    <div class="actions">
      <button class="primary" @click="save">{{ t('common.save') }}</button>
    </div>
  </div>
  <p v-else>{{ t('common.loading') }}</p>
</template>

<style scoped>
.form {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 10px 0 16px;
  max-width: 520px;
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 10px;
  border: 1px solid transparent;
  border-radius: 3px;
  min-height: 32px;
}

.row:hover {
  background: var(--row-alt);
  border-color: var(--border);
}

.row.check {
  justify-content: flex-start;
}

.row.check input[type="checkbox"] {
  margin: 0;
  flex: 0 0 auto;
}

.label-text {
  font-size: 13px;
  color: var(--text);
}

.num {
  width: 100px;
  text-align: right;
  font-family: var(--mono);
  flex: 0 0 100px;
}
.pw {
  width: 200px;
  font-family: var(--mono);
  flex: 0 0 200px;
}
.host {
  width: 160px;
  font-family: var(--mono);
  flex: 0 0 160px;
}
.host:disabled { opacity: 0.5; cursor: not-allowed; }
.security-title { margin-top: 18px; }
.hint { color: var(--text-dim); font-size: 12px; margin: 4px 10px; }

.lang-select {
  width: 100px;
  flex: 0 0 100px;
}

.actions {
  padding-top: 8px;
  border-top: 1px solid var(--border);
  margin-top: 8px;
}

.saved-msg {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin: 8px 0;
  padding: 5px 10px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 3px;
  color: #166534;
  font-size: 12.5px;
}

.saved-time {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--text-dim);
}
</style>
