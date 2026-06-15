<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const { t } = useI18n()
const devices = ref([])
const curves = ref([])
const assignments = ref({})
const error = ref('')

async function load() {
  try {
    const [d, c, a] = await Promise.all([
      api.listDevices(),
      api.listCurves(),
      api.getAssignments(),
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
    await load()
  } catch (e) { error.value = e.message }
}

onMounted(load)
</script>

<template>
  <div>
    <h2>{{ t('assignments.title') }}</h2>
    <div class="error" v-if="error">{{ error }}</div>
    <table class="section">
      <thead>
        <tr>
          <th>{{ t('assignments.device') }}</th>
          <th>{{ t('assignments.curve') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in devices" :key="d.id">
          <td>{{ d.name }} ({{ d.id }})</td>
          <td>
            <select
              :value="assignments[d.id] || ''"
              @change="setAssignment(d.id, $event.target.value)"
            >
              <option value="">— {{ t('common.none') }} —</option>
              <option v-for="c in curves" :key="c.id" :value="c.id">{{ c.name }} ({{ c.id }})</option>
            </select>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
