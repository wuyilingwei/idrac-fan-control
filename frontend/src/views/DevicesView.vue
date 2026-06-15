<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const { t } = useI18n()
const devices = ref([])
const curves = ref([])
const assignments = ref({})
const error = ref('')
const editing = ref(null)
const availableSensors = ref([])

const emptyDevice = () => ({
  id: '', name: '', host: '', user: 'root', password: '',
  backend: 'ipmi', info: {}, verify_tls: false,
  temp_strategy: 'max', temp_sensors: [],
})

async function load() {
  try {
    const [d, c, a] = await Promise.all([
      api.listDevices(), api.listCurves(), api.getAssignments(),
    ])
    devices.value = d
    curves.value = c
    assignments.value = a
    error.value = ''
  } catch (e) { error.value = e.message }
}

async function setAssignment(deviceId, curveId) {
  try {
    await api.setAssignment(deviceId, curveId || null)
    assignments.value = await api.getAssignments()
  } catch (e) { error.value = e.message }
}

function startNew() { editing.value = emptyDevice(); availableSensors.value = [] }
function startEdit(d) {
  editing.value = JSON.parse(JSON.stringify({
    ...emptyDevice(), ...d,
    temp_sensors: d.temp_sensors || [],
  }))
  availableSensors.value = []
  // 编辑现存设备时,立即去拿可选 sensors(R730 已经连)
  if (d.id) loadSensors(d.id)
}
function cancel() { editing.value = null }

async function loadSensors(id) {
  try {
    const r = await api.listSensors(id)
    availableSensors.value = r.temps || []
  } catch (e) {
    // 静默 — 后端可能没连
    availableSensors.value = []
  }
}

function toggleSensor(name) {
  const arr = editing.value.temp_sensors
  const i = arr.indexOf(name)
  if (i === -1) arr.push(name); else arr.splice(i, 1)
}

async function save() {
  try {
    const d = editing.value
    if (devices.value.some((x) => x.id === d.id)) {
      await api.updateDevice(d.id, d)
    } else {
      await api.createDevice(d)
    }
    editing.value = null
    await load()
  } catch (e) { error.value = e.message }
}

async function remove(id) {
  if (!confirm(`Delete device ${id}?`)) return
  try { await api.deleteDevice(id); await load() }
  catch (e) { error.value = e.message }
}

async function probe(id) {
  try {
    const info = await api.probe(id)
    alert(`Probed: ${JSON.stringify(info, null, 2)}`)
    await load()
  } catch (e) { error.value = e.message }
}

async function fanManual(id) {
  const pctStr = prompt(t('devices.pct_input'))
  if (pctStr === null) return
  const pct = parseInt(pctStr, 10)
  if (isNaN(pct)) return
  try { await api.fanManual(id, pct) } catch (e) { error.value = e.message }
}

async function fanAuto(id) {
  try { await api.fanAuto(id) } catch (e) { error.value = e.message }
}

onMounted(load)
</script>

<template>
  <div>
    <h2>{{ t('devices.title') }}</h2>
    <p class="warn">{{ t('devices.warn_plaintext') }}</p>
    <div class="error" v-if="error">{{ error }}</div>

    <button class="primary" @click="startNew" v-if="!editing">+ {{ t('common.add') }}</button>

    <div v-if="editing" class="section">
      <h3>{{ editing.id ? t('common.edit') : t('common.add') }}</h3>
      <p><label>{{ t('devices.id') }} <input v-model="editing.id" :disabled="devices.some((d) => d.id === editing.id)" /></label></p>
      <p><label>{{ t('devices.name') }} <input v-model="editing.name" /></label></p>
      <p><label>{{ t('devices.host') }} <input v-model="editing.host" /></label></p>
      <p><label>{{ t('devices.user') }} <input v-model="editing.user" /></label></p>
      <p><label>{{ t('devices.password') }} <input v-model="editing.password" type="password" /></label></p>
      <p><label>{{ t('devices.backend') }}
        <select v-model="editing.backend">
          <option value="ipmi">IPMI</option>
          <option value="redfish_oem">Redfish OEM</option>
        </select>
      </label></p>
      <p><label>{{ t('devices.verify_tls') }} <input type="checkbox" v-model="editing.verify_tls" /></label></p>

      <h4 style="margin-top:14px;">{{ t('devices.temp_strategy') }}</h4>
      <p><label>
        <select v-model="editing.temp_strategy">
          <option value="max">{{ t('devices.strategy_max') }}</option>
          <option value="avg">{{ t('devices.strategy_avg') }}</option>
        </select>
      </label>
      <button v-if="editing.id" @click="loadSensors(editing.id)" style="margin-left:8px;">
        {{ t('devices.refresh_sensors') }}
      </button>
      </p>
      <div style="margin: 8px 0 14px;">
        <p class="hint" style="margin-bottom:6px;">{{ t('devices.participating_sensors_hint') }}</p>
        <div v-if="availableSensors.length > 0" class="sensor-grid">
          <label v-for="s in availableSensors" :key="s.name" class="sensor-chip">
            <input type="checkbox"
                   :checked="editing.temp_sensors.includes(s.name)"
                   @change="toggleSensor(s.name)" />
            <span class="sensor-name">{{ s.name }}</span>
            <span class="sensor-val">{{ s.value_c.toFixed(1) }} °C</span>
          </label>
        </div>
        <p v-else class="hint">{{ t('devices.sensors_unavailable') }}</p>
      </div>

      <button class="primary" @click="save">{{ t('common.save') }}</button>
      <button @click="cancel" style="margin-left: 6px;">{{ t('common.cancel') }}</button>
    </div>

    <table class="section">
      <thead>
        <tr>
          <th>{{ t('devices.id') }}</th>
          <th>{{ t('devices.name') }}</th>
          <th>{{ t('devices.host') }}</th>
          <th>{{ t('devices.model') }}</th>
          <th>{{ t('devices.idrac_label') }}</th>
          <th>{{ t('devices.host_os') }}</th>
          <th>{{ t('assignments.curve') }}</th>
          <th>actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in devices" :key="d.id">
          <td>{{ d.id }}</td>
          <td>{{ d.name }}</td>
          <td>{{ d.host }}</td>
          <td>{{ d.info?.model || '—' }}<br>
            <span style="color:#6e6e73;font-size:11px;">{{ d.info?.service_tag || '' }}</span>
          </td>
          <td>
            <span v-if="d.info?.idrac_gen">iDRAC{{ d.info.idrac_gen }}</span>
            <span v-else>—</span><br>
            <span style="color:#6e6e73;font-size:11px;">{{ d.info?.idrac_firmware || '' }}</span>
          </td>
          <td>{{ d.info?.host_os || '—' }}</td>
          <td>
            <select
              :value="assignments[d.id] || ''"
              @change="setAssignment(d.id, $event.target.value)"
            >
              <option value="">— {{ t('common.none') }} —</option>
              <option v-for="c in curves" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </td>
          <td>
            <button @click="startEdit(d)">{{ t('common.edit') }}</button>
            <button @click="probe(d.id)">{{ t('devices.probe') }}</button>
            <button @click="fanManual(d.id)">{{ t('devices.fan_manual') }}</button>
            <button @click="fanAuto(d.id)">{{ t('devices.fan_auto') }}</button>
            <button class="danger" @click="remove(d.id)">{{ t('common.delete') }}</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.hint { color: #6e6e73; font-size: 12px; margin: 4px 0; }
h4 { margin: 14px 0 6px; font-size: 13px; color: #444; text-transform: uppercase; letter-spacing: 0.04em; }
.sensor-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 6px; }
.sensor-chip {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px;
  border: 1px solid #d4d4d8;
  border-radius: 4px;
  background: #fafafa;
  font-size: 13px;
  cursor: pointer;
}
.sensor-chip:hover { background: #f0f0f3; border-color: #a1a1aa; }
.sensor-chip input[type="checkbox"] { margin: 0; }
.sensor-name { flex: 1; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.sensor-val { color: #6e6e73; font-size: 12px; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
</style>
