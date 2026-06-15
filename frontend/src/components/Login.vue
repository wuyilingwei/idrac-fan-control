<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api.js'

const { t } = useI18n()
const emit = defineEmits(['logged-in'])
const password = ref('')
const error = ref('')
const submitting = ref(false)

async function submit() {
  if (!password.value || submitting.value) return
  submitting.value = true
  error.value = ''
  try {
    const r = await api.login(password.value)
    if (r.token) {
      localStorage.setItem('auth_token', r.token)
      emit('logged-in')
    } else {
      // auth 未启用,直接通过
      emit('logged-in')
    }
  } catch (e) {
    error.value = e.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="card">
      <h1>{{ t('app.title') }}</h1>
      <p class="hint">{{ t('login.hint') }}</p>
      <input
        type="password"
        v-model="password"
        :placeholder="t('login.password_placeholder')"
        @keydown.enter="submit"
        autofocus
      />
      <button class="primary" :disabled="submitting || !password" @click="submit">
        {{ submitting ? t('common.loading') : t('login.submit') }}
      </button>
      <div v-if="error" class="error">{{ error }}</div>
    </div>
  </div>
</template>

<style scoped>
.login {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f5f7;
}
.card {
  background: white;
  padding: 32px;
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  width: 320px;
}
.card h1 { margin: 0 0 8px; font-size: 18px; font-weight: 600; }
.card .hint { color: #6e6e73; font-size: 13px; margin-bottom: 16px; }
.card input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #c7c7cc;
  border-radius: 6px;
  font-size: 14px;
  margin-bottom: 12px;
}
.card button.primary {
  width: 100%;
  background: #0066cc;
  color: white;
  border: none;
  padding: 10px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}
.card button.primary:disabled { opacity: 0.4; cursor: not-allowed; }
.error { color: #d32f2f; margin-top: 12px; font-size: 13px; }
</style>
