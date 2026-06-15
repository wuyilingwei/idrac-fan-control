<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const { t } = useI18n()
const status = ref({ last_tick: {}, devices: [] })
const error = ref('')
let timer = null

async function refresh() {
  try {
    status.value = await api.getStatus()
    error.value = ''
  } catch (e) {
    error.value = e.message
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 3000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="status-view">
    <div class="header-row">
      <h2>{{ t('status.title') }}</h2>
      <button class="primary" @click="refresh">{{ t('status.refresh') }}</button>
    </div>
    <div class="error" v-if="error">{{ error }}</div>
    <p v-if="Object.keys(status.last_tick).length === 0" class="warn">{{ t('status.no_data') }}</p>
    <table v-else class="section status-table">
      <thead>
        <tr>
          <th>{{ t('status.device') }}</th>
          <th class="col-num">{{ t('status.temp') }}</th>
          <th class="col-num">{{ t('status.target_pct') }}</th>
          <th>{{ t('status.tick_status') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(tr, id) in status.last_tick" :key="id">
          <td class="col-id">{{ id }}</td>
          <td class="col-num">{{ tr.temp !== null ? tr.temp.toFixed(1) + ' °C' : '—' }}</td>
          <td class="col-num">{{ tr.target_pct !== null ? tr.target_pct + ' %' : '—' }}</td>
          <td>{{ tr.status }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.header-row h2 {
  margin: 0;
  padding-bottom: 0;
  border-bottom: none;
  flex: 1;
}
.status-table .col-num {
  font-family: var(--mono);
  white-space: nowrap;
}
.status-table .col-id {
  font-family: var(--mono);
  color: var(--text-dim);
}
.status-table th.col-num {
  font-family: inherit;
}
</style>
