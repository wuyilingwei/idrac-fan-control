// api.js — fetch wrapper, 所有调用走 /api/* (dev 模式由 vite proxy 转发到 :8080).
// 错误码语义见 app/main.py findings.md.

const BASE = '/api'

async function request(path, { method = 'GET', body, headers = {} } = {}) {
  const opts = { method, headers: { 'Content-Type': 'application/json', ...headers } }
  const token = localStorage.getItem('auth_token')
  if (token) opts.headers['Authorization'] = `Bearer ${token}`
  if (body !== undefined) opts.body = JSON.stringify(body)
  const res = await fetch(BASE + path, opts)
  let payload = null
  const txt = await res.text()
  if (txt) {
    try { payload = JSON.parse(txt) } catch { payload = txt }
  }
  if (res.status === 401) {
    // token 失效 → 清掉 + 触发全局事件让 App 重渲染到登陆
    localStorage.removeItem('auth_token')
    window.dispatchEvent(new CustomEvent('idrac-unauthorized'))
  }
  if (!res.ok) {
    const err = new Error(`API ${res.status}: ${(payload && payload.detail) || res.statusText}`)
    err.status = res.status
    err.payload = payload
    throw err
  }
  return payload
}

export const api = {
  // auth
  authStatus: () => request('/auth/status'),
  login: (password) => request('/auth/login', { method: 'POST', body: { password } }),
  logout: () => request('/auth/logout', { method: 'POST' }),

  // health & config
  health: () => request('/health'),
  getConfig: () => request('/config'),
  putConfig: (cfg) => request('/config', { method: 'PUT', body: cfg }),

  // devices
  listDevices: () => request('/devices'),
  getDevice: (id) => request(`/devices/${encodeURIComponent(id)}`),
  createDevice: (d) => request('/devices', { method: 'POST', body: d }),
  updateDevice: (id, d) => request(`/devices/${encodeURIComponent(id)}`, { method: 'PUT', body: d }),
  deleteDevice: (id) => request(`/devices/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // curves
  listCurves: () => request('/curves'),
  getCurve: (id) => request(`/curves/${encodeURIComponent(id)}`),
  createCurve: (c) => request('/curves', { method: 'POST', body: c }),
  updateCurve: (id, c) => request(`/curves/${encodeURIComponent(id)}`, { method: 'PUT', body: c }),
  deleteCurve: (id) => request(`/curves/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // assignments
  getAssignments: () => request('/assignments'),
  setAssignment: (deviceId, curveId) =>
    request(`/assignments/${encodeURIComponent(deviceId)}`, { method: 'PUT', body: { curve_id: curveId } }),

  // settings
  getSettings: () => request('/settings'),
  updateSettings: (patch) => request('/settings', { method: 'PUT', body: patch }),

  // status & control
  getStatus: () => request('/status'),
  fanManual: (deviceId, pct) =>
    request(`/devices/${encodeURIComponent(deviceId)}/fan/manual`, { method: 'POST', body: { pct } }),
  fanAuto: (deviceId) =>
    request(`/devices/${encodeURIComponent(deviceId)}/fan/auto`, { method: 'POST', body: {} }),
  probe: (deviceId) =>
    request(`/devices/${encodeURIComponent(deviceId)}/probe`, { method: 'POST', body: {} }),
  listSensors: (deviceId) =>
    request(`/devices/${encodeURIComponent(deviceId)}/sensors`),

  // notifier test
  testNotifier: (notifierId, event, ctx) =>
    request('/notifiers/test', { method: 'POST', body: { notifier_id: notifierId, event, ctx: ctx || {} } }),
}
