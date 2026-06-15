<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'
import CurveEditor from '../components/CurveEditor.vue'

const { t } = useI18n()
const curves = ref([])
const assignments = ref({})
const status = ref({ last_tick: {}, devices: [] })
const error = ref('')
const editing = ref(null)
const editingIsNew = ref(false)
let statusTimer = null

// 编辑某曲线时,找出第一个分配到此曲线的 device 的实时 tick 结果
const liveForEditing = computed(() => {
  if (!editing.value) return null
  const curveId = editing.value.id
  const deviceId = Object.entries(assignments.value).find(([, c]) => c === curveId)?.[0]
  if (!deviceId) return null
  const tr = status.value.last_tick?.[deviceId]
  if (!tr) return null
  return { temp: tr.temp, target_pct: tr.target_pct, status: tr.status }
})

async function refreshStatus() {
  try {
    const [a, s] = await Promise.all([api.getAssignments(), api.getStatus()])
    assignments.value = a
    status.value = s
  } catch { /* 静默 */ }
}

const emptyCurve = () => ({
  id: '', name: '', mode: 'linear',
  points: [
    { temp: 30, pct: 15 },
    { temp: 50, pct: 30 },
    { temp: 70, pct: 60 },
    { temp: 80, pct: 100 },
  ],
})

async function load() {
  try { curves.value = await api.listCurves(); error.value = '' }
  catch (e) { error.value = e.message }
}

function startNew() { editing.value = emptyCurve(); editingIsNew.value = true }
function startEdit(c) { editing.value = JSON.parse(JSON.stringify(c)); editingIsNew.value = false }
function cancel() { editing.value = null; editingIsNew.value = false }

async function save() {
  try {
    const c = editing.value
    if (editingIsNew.value) await api.createCurve(c)
    else await api.updateCurve(c.id, c)
    editing.value = null
    editingIsNew.value = false
    await load()
  } catch (e) { error.value = e.message }
}

async function remove(id) {
  if (!confirm(`Delete curve ${id}?`)) return
  try { await api.deleteCurve(id); await load() }
  catch (e) { error.value = e.message }
}

onMounted(() => {
  load()
  refreshStatus()
  statusTimer = setInterval(refreshStatus, 3000)
})
onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer)
})
</script>

<template>
  <div>
    <div class="title-bar">
      <h2>{{ t('curves.title') }}</h2>
      <button class="primary" @click="startNew" v-if="!editing">+ {{ t('common.add') }}</button>
    </div>
    <div class="error" v-if="error">{{ error }}</div>

    <div v-if="editing" class="section editor-panel">
      <h3>{{ editingIsNew ? t('common.add') : t('common.edit') }}</h3>
      <CurveEditor v-model="editing" :live="liveForEditing" />
      <div class="actions">
        <button class="primary" @click="save">{{ t('common.save') }}</button>
        <button @click="cancel">{{ t('common.cancel') }}</button>
      </div>
    </div>

    <table class="section curves-table">
      <thead>
        <tr>
          <th class="col-id">{{ t('curves.id') }}</th>
          <th class="col-name">{{ t('curves.name') }}</th>
          <th class="col-mode">{{ t('curves.mode') }}</th>
          <th class="col-points">{{ t('curves.points') }}</th>
          <th class="col-actions">actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in curves" :key="c.id">
          <td class="col-id mono">{{ c.id }}</td>
          <td class="col-name">{{ c.name }}</td>
          <td class="col-mode">
            <span
              class="mode-tag"
              :class="c.mode === 'step' ? 'mode-step' : 'mode-linear'"
            >{{ t(c.mode === 'step' ? 'curves.mode_step' : 'curves.mode_linear') }}</span>
          </td>
          <td class="col-points mono">{{ c.points.length }}</td>
          <td class="col-actions">
            <button @click="startEdit(c)">{{ t('common.edit') }}</button>
            <button class="danger" @click="remove(c.id)">{{ t('common.delete') }}</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.title-bar h2 {
  margin: 0 0 14px;
  flex: 1;
}
.title-bar .primary {
  margin-bottom: 14px;
}

.editor-panel .actions {
  margin-top: 12px;
  display: flex;
  gap: 6px;
}

.curves-table {
  table-layout: fixed;
}
.curves-table .col-id { width: 18%; }
.curves-table .col-name { width: 30%; }
.curves-table .col-mode { width: 12%; }
.curves-table .col-points { width: 10%; text-align: right; }
.curves-table .col-actions { width: 30%; }

.mono {
  font-family: var(--mono);
}

.mode-tag {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border-radius: 3px;
  border: 1px solid var(--border);
  font-family: var(--mono);
  line-height: 1.4;
}
.mode-tag.mode-linear {
  color: var(--accent);
  border-color: var(--accent);
  background: rgba(31, 111, 235, 0.08);
}
.mode-tag.mode-step {
  color: var(--text-dim);
  border-color: var(--border-strong);
  background: var(--row-alt);
}
</style>
