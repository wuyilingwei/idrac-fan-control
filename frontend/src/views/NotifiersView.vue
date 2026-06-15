<script setup>
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const { t } = useI18n()
const cfg = ref(null)
const error = ref('')
const editing = ref(null)
const editingIdx = ref(-1)

const EVENTS = ['overtemp_alert', 'failsafe_trip', 'connection_lost', 'command_failed']

const emptyNotifier = () => ({
  id: '', type: 'telegram', enabled: true,
  events: ['overtemp_alert'],
  config: { bot_token: '', chat_id: '' },
})

async function load() {
  try { cfg.value = await api.getConfig(); error.value = '' }
  catch (e) { error.value = e.message }
}

function startNew() {
  editing.value = emptyNotifier()
  editingIdx.value = -1
}

function startEdit(n, i) {
  editing.value = JSON.parse(JSON.stringify(n))
  editingIdx.value = i
}

function cancel() {
  editing.value = null
  editingIdx.value = -1
}

async function save() {
  try {
    const newCfg = JSON.parse(JSON.stringify(cfg.value))
    if (editingIdx.value === -1) newCfg.notifiers.push(editing.value)
    else newCfg.notifiers[editingIdx.value] = editing.value
    await api.putConfig(newCfg)
    editing.value = null
    editingIdx.value = -1
    await load()
  } catch (e) { error.value = e.message }
}

async function remove(i) {
  if (!confirm('Delete?')) return
  try {
    const newCfg = JSON.parse(JSON.stringify(cfg.value))
    newCfg.notifiers.splice(i, 1)
    await api.putConfig(newCfg)
    await load()
  } catch (e) { error.value = e.message }
}

async function test(notifierId) {
  try {
    await api.testNotifier(notifierId, 'overtemp_alert', { device_name: 'test', temp: 85 })
    alert('Test dispatched.')
  } catch (e) { error.value = e.message }
}

function toggleEvent(ev) {
  if (!editing.value) return
  const idx = editing.value.events.indexOf(ev)
  if (idx === -1) editing.value.events.push(ev)
  else editing.value.events.splice(idx, 1)
}

function changeType(t) {
  editing.value.type = t
  editing.value.config = t === 'telegram'
    ? { bot_token: '', chat_id: '' }
    : { method: 'POST', url: '', headers: {}, body_template: '{message}' }
}

function typeIcon(type) {
  if (type === 'telegram') return '✈'
  if (type === 'webhook') return '⇄'
  return '•'
}

const configJson = computed({
  get: () => JSON.stringify(editing.value?.config || {}, null, 2),
  set: (v) => {
    try { editing.value.config = JSON.parse(v) }
    catch { /* keep last valid */ }
  },
})

onMounted(load)
</script>

<template>
  <div v-if="cfg">
    <h2>{{ t('notifiers.title') }}</h2>
    <div class="error" v-if="error">{{ error }}</div>

    <button class="primary" @click="startNew" v-if="!editing">+ {{ t('common.add') }}</button>

    <div v-if="editing" class="section editor">
      <h3>{{ editingIdx === -1 ? t('common.add') : t('common.edit') }}</h3>
      <p><label>{{ t('notifiers.id') }} <input v-model="editing.id" /></label></p>
      <p><label>{{ t('notifiers.type') }}
        <select :value="editing.type" @change="changeType($event.target.value)">
          <option value="telegram">{{ t('notifiers.type_telegram') }}</option>
          <option value="webhook">{{ t('notifiers.type_webhook') }}</option>
        </select>
      </label></p>
      <p><label>
        <input type="checkbox" v-model="editing.enabled" />
        {{ t('notifiers.enabled') }}
      </label></p>
      <p class="events-label">{{ t('notifiers.events') }}:</p>
      <div class="events-grid">
        <label v-for="ev in EVENTS" :key="ev" class="event-chip">
          <input type="checkbox" :checked="editing.events.includes(ev)" @change="toggleEvent(ev)" />
          <span>{{ ev }}</span>
        </label>
      </div>
      <p class="config-label">{{ t('notifiers.config') }}:</p>
      <textarea v-model="configJson" rows="6" class="config-json"></textarea>
      <div class="actions-row">
        <button class="primary" @click="save">{{ t('common.save') }}</button>
        <button @click="cancel">{{ t('common.cancel') }}</button>
      </div>
    </div>

    <table class="section">
      <thead>
        <tr>
          <th>{{ t('notifiers.id') }}</th>
          <th>{{ t('notifiers.type') }}</th>
          <th class="col-enabled">{{ t('notifiers.enabled') }}</th>
          <th>{{ t('notifiers.events') }}</th>
          <th>actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(n, i) in cfg.notifiers" :key="i">
          <td class="cell-id">{{ n.id }}</td>
          <td>
            <span class="type-icon" :title="n.type">{{ typeIcon(n.type) }}</span>
            <span class="type-label">{{ n.type }}</span>
          </td>
          <td class="col-enabled">
            <span
              class="status-dot"
              :class="n.enabled ? 'on' : 'off'"
              :title="n.enabled ? t('common.yes') : t('common.no')"
            ></span>
          </td>
          <td class="cell-events">{{ n.events.join(', ') }}</td>
          <td class="cell-actions">
            <button @click="startEdit(n, i)">{{ t('common.edit') }}</button>
            <button @click="test(n.id)">{{ t('common.test') }}</button>
            <button class="danger" @click="remove(i)">{{ t('common.delete') }}</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <p v-else>{{ t('common.loading') }}</p>
</template>

<style scoped>
.editor {
  border: 1px solid var(--border);
  background: var(--panel);
  padding: 12px 14px;
  border-radius: 3px;
}

.events-label,
.config-label {
  margin: 10px 0 6px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-dim);
}

.events-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin: 4px 0 10px;
}

.event-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: var(--row-alt);
  font-size: 12.5px;
  font-family: var(--mono);
  color: var(--text);
  cursor: pointer;
  transition: border-color 0.12s, background 0.12s;
}
.event-chip:hover { border-color: var(--border-strong); }
.event-chip input[type="checkbox"] { margin: 0; }

.config-json {
  width: 100%;
  font-family: var(--mono);
  font-size: 12.5px;
  line-height: 1.45;
  background: var(--row-alt);
  color: var(--text);
}

.actions-row {
  margin-top: 10px;
  display: flex;
  gap: 6px;
}

/* === Table cells === */
.cell-id { font-family: var(--mono); font-weight: 500; }
.cell-events { font-family: var(--mono); color: var(--text-dim); font-size: 12px; }
.cell-actions { white-space: nowrap; }

.type-icon {
  display: inline-block;
  width: 16px;
  text-align: center;
  margin-right: 6px;
  color: var(--text-dim);
  font-family: var(--mono);
}
.type-label { font-family: var(--mono); font-size: 12.5px; }

.col-enabled { width: 70px; text-align: center; }

.status-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1px solid var(--border-strong);
  vertical-align: middle;
}
.status-dot.on {
  background: #16a34a;
  border-color: #15803d;
  box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.15);
}
.status-dot.off {
  background: #d4d4d8;
  border-color: var(--border-strong);
}
</style>
