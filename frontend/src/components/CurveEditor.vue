<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  modelValue: { type: Object, required: true },
  live: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue'])

const localCurve = ref(JSON.parse(JSON.stringify(props.modelValue)))
watch(() => props.modelValue, (v) => {
  localCurve.value = JSON.parse(JSON.stringify(v))
}, { deep: true })

function emitChange() {
  localCurve.value.points.sort((a, b) => a.temp - b.temp)
  emit('update:modelValue', JSON.parse(JSON.stringify(localCurve.value)))
}

const sortedPoints = computed(() =>
  [...localCurve.value.points].sort((a, b) => a.temp - b.temp)
)

// 容器尺寸响应式跟踪 — viewBox 单位 = 物理 px,圆点 / 文字保持自然大小
const svgRef = ref(null)
const dim = ref({ w: 800, h: 520 })
let resizeObserver = null

// 内边距(像素),留出 X/Y 标签空间
const PAD = { l: 56, r: 18, t: 14, b: 40 }

const dataArea = computed(() => ({
  x: PAD.l,
  y: PAD.t,
  w: Math.max(10, dim.value.w - PAD.l - PAD.r),
  h: Math.max(10, dim.value.h - PAD.t - PAD.b),
}))

// 数据 (temp, pct) ∈ [0,100]² → SVG px
function tx(temp) {
  return dataArea.value.x + (temp / 100) * dataArea.value.w
}
function ty(pct) {
  return dataArea.value.y + ((100 - pct) / 100) * dataArea.value.h
}

const X_MAJOR = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
const Y_MAJOR = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
const X_MINOR = [5, 15, 25, 35, 45, 55, 65, 75, 85, 95]
const Y_MINOR = [5, 15, 25, 35, 45, 55, 65, 75, 85, 95]

function svgPath() {
  const pts = sortedPoints.value
  if (pts.length === 0) return ''
  const first = pts[0], last = pts[pts.length - 1]
  if (localCurve.value.mode === 'step') {
    const segs = [`M ${tx(0)} ${ty(first.pct)}`, `L ${tx(first.temp)} ${ty(first.pct)}`]
    for (let i = 1; i < pts.length; i++) {
      const prev = pts[i - 1], cur = pts[i]
      segs.push(`L ${tx(cur.temp)} ${ty(prev.pct)}`)
      segs.push(`L ${tx(cur.temp)} ${ty(cur.pct)}`)
    }
    segs.push(`L ${tx(100)} ${ty(last.pct)}`)
    return segs.join(' ')
  }
  const segs = [`M ${tx(0)} ${ty(first.pct)}`]
  for (const p of pts) segs.push(`L ${tx(p.temp)} ${ty(p.pct)}`)
  segs.push(`L ${tx(100)} ${ty(last.pct)}`)
  return segs.join(' ')
}

// 拖动
const dragging = ref(null)

function startDrag(sortedIdx, event) {
  const target = sortedPoints.value[sortedIdx]
  if (!target) return
  const rawIdx = localCurve.value.points.findIndex(
    (p) => p.temp === target.temp && p.pct === target.pct,
  )
  if (rawIdx === -1) return
  dragging.value = { rawIdx, sortedIdx }
  event.preventDefault()
  event.stopPropagation()
}

function clientToData(event) {
  const svg = event.currentTarget
  const r = svg.getBoundingClientRect()
  const px = event.clientX - r.left
  const py = event.clientY - r.top
  // SVG viewBox 现在 == 物理 px,所以 px 直接是 SVG 单位
  const temp = Math.max(0, Math.min(100, Math.round(((px - PAD.l) / dataArea.value.w) * 100)))
  const pct = Math.max(0, Math.min(100, Math.round(100 - ((py - PAD.t) / dataArea.value.h) * 100)))
  return { temp, pct }
}

function onMove(event) {
  if (!dragging.value) return
  const { rawIdx, sortedIdx } = dragging.value
  const { temp: rawTemp, pct } = clientToData(event)
  const prev = sortedPoints.value[sortedIdx - 1]
  const next = sortedPoints.value[sortedIdx + 1]
  const minTemp = prev ? prev.temp : 0
  const maxTemp = next ? next.temp : 100
  const temp = Math.max(minTemp, Math.min(maxTemp, rawTemp))
  if (rawIdx >= 0 && rawIdx < localCurve.value.points.length) {
    localCurve.value.points[rawIdx].temp = temp
    localCurve.value.points[rawIdx].pct = pct
  }
}

function endDrag() {
  if (dragging.value !== null) {
    dragging.value = null
    emitChange()
  }
}

function onContextMenu(event) {
  event.preventDefault()
  if (dragging.value !== null) return
  const { temp, pct } = clientToData(event)
  // 只在数据区内加点(避开 padding 区域)
  const svg = event.currentTarget
  const r = svg.getBoundingClientRect()
  const px = event.clientX - r.left
  const py = event.clientY - r.top
  if (px < PAD.l || px > dim.value.w - PAD.r || py < PAD.t || py > dim.value.h - PAD.b) return
  localCurve.value.points.push({ temp, pct })
  emitChange()
}

function _rawIdxOfSorted(sortedIdx) {
  const t = sortedPoints.value[sortedIdx]
  return t ? localCurve.value.points.findIndex(p => p.temp === t.temp && p.pct === t.pct) : -1
}

function addRow() {
  localCurve.value.points.push({ temp: 50, pct: 50 })
  emitChange()
}

function updateRow(sortedIdx, field, value) {
  const v = parseInt(value, 10)
  if (isNaN(v)) return
  const rawIdx = _rawIdxOfSorted(sortedIdx)
  if (rawIdx === -1) return
  localCurve.value.points[rawIdx][field] = v
  emitChange()
}

function removeRow(sortedIdx) {
  const rawIdx = _rawIdxOfSorted(sortedIdx)
  if (rawIdx === -1) return
  localCurve.value.points.splice(rawIdx, 1)
  emitChange()
}

function removePoint(sortedIdx) {
  removeRow(sortedIdx)
}

function changeMode(mode) {
  localCurve.value.mode = mode
  emitChange()
}

const liveTemp = computed(() => props.live && props.live.temp !== null && props.live.temp !== undefined ? Number(props.live.temp) : null)
const liveTarget = computed(() => props.live && props.live.target_pct !== null && props.live.target_pct !== undefined ? Number(props.live.target_pct) : null)

onMounted(() => {
  if (svgRef.value) {
    resizeObserver = new ResizeObserver((entries) => {
      for (const e of entries) {
        const cr = e.contentRect
        dim.value = { w: Math.max(200, cr.width), h: Math.max(200, cr.height) }
      }
    })
    resizeObserver.observe(svgRef.value)
    // 初始化
    const r = svgRef.value.getBoundingClientRect()
    if (r.width && r.height) dim.value = { w: r.width, h: r.height }
  }
})
onUnmounted(() => {
  if (resizeObserver) { resizeObserver.disconnect(); resizeObserver = null }
})
</script>

<template>
  <div class="curve-editor">
    <div class="meta">
      <label>
        <span class="meta-key">{{ t('curves.id') }}</span>
        <input v-model="localCurve.id" @change="emitChange" />
      </label>
      <label>
        <span class="meta-key">{{ t('curves.name') }}</span>
        <input v-model="localCurve.name" @change="emitChange" />
      </label>
      <label>
        <span class="meta-key">{{ t('curves.mode') }}</span>
        <select :value="localCurve.mode" @change="changeMode($event.target.value)">
          <option value="linear">{{ t('curves.mode_linear') }}</option>
          <option value="step">{{ t('curves.mode_step') }}</option>
        </select>
      </label>
    </div>

    <svg
      ref="svgRef"
      class="canvas"
      :viewBox="`0 0 ${dim.w} ${dim.h}`"
      preserveAspectRatio="none"
      @mousemove="onMove"
      @mouseup="endDrag"
      @mouseleave="endDrag"
      @contextmenu="onContextMenu"
    >
      <!-- 数据区背景 -->
      <rect :x="dataArea.x" :y="dataArea.y" :width="dataArea.w" :height="dataArea.h"
            fill="#fafafa" stroke="#c7c7cc" stroke-width="1" />
      <!-- 网格 minor -->
      <g class="grid-minor">
        <line v-for="x in X_MINOR" :key="'vm'+x" :x1="tx(x)" :y1="ty(100)" :x2="tx(x)" :y2="ty(0)" />
        <line v-for="y in Y_MINOR" :key="'hm'+y" :x1="tx(0)" :y1="ty(y)" :x2="tx(100)" :y2="ty(y)" />
      </g>
      <!-- 网格 major -->
      <g class="grid">
        <line v-for="x in X_MAJOR" :key="'v'+x" :x1="tx(x)" :y1="ty(100)" :x2="tx(x)" :y2="ty(0)" />
        <line v-for="y in Y_MAJOR" :key="'h'+y" :x1="tx(0)" :y1="ty(y)" :x2="tx(100)" :y2="ty(y)" />
      </g>
      <!-- X 轴标签 -->
      <g class="axis-labels">
        <text v-for="x in X_MAJOR" :key="'xl'+x" :x="tx(x)" :y="dataArea.y + dataArea.h + 14"
              text-anchor="middle">{{ x }}</text>
        <text :x="dataArea.x + dataArea.w / 2" :y="dim.h - 6" text-anchor="middle" class="axis-title">温度 °C</text>
      </g>
      <!-- Y 轴标签 -->
      <g class="axis-labels">
        <text v-for="y in Y_MAJOR" :key="'yl'+y" :x="dataArea.x - 6" :y="ty(y) + 4"
              text-anchor="end">{{ y }}</text>
        <text :x="14" :y="dataArea.y + dataArea.h / 2" text-anchor="middle" class="axis-title"
              :transform="`rotate(-90 14 ${dataArea.y + dataArea.h / 2})`">风扇 %</text>
      </g>
      <!-- 实时叠加 -->
      <g v-if="liveTemp !== null" class="live-overlay">
        <line :x1="tx(liveTemp)" :y1="ty(100)" :x2="tx(liveTemp)" :y2="ty(0)" />
        <line v-if="liveTarget !== null" :x1="tx(0)" :y1="ty(liveTarget)" :x2="tx(100)" :y2="ty(liveTarget)" />
        <circle v-if="liveTarget !== null" :cx="tx(liveTemp)" :cy="ty(liveTarget)" r="5" />
        <text :x="tx(liveTemp) + 6" :y="dataArea.y + 12" class="live-label">{{ liveTemp.toFixed(1) }}°C{{ liveTarget !== null ? ` → ${liveTarget}%` : '' }}</text>
      </g>
      <!-- 曲线 -->
      <path :d="svgPath()" stroke="#0066cc" fill="none" stroke-width="2" />
      <!-- 点 -->
      <circle
        v-for="(p, i) in sortedPoints"
        :key="i"
        :cx="tx(p.temp)"
        :cy="ty(p.pct)"
        r="6"
        fill="#0066cc"
        stroke="white"
        stroke-width="1.5"
        class="grab"
        @mousedown.stop="startDrag(i, $event)"
        @dblclick.stop="removePoint(i)"
      />
    </svg>
    <p class="hint">右键空白加点 · 双击点删除 · 拖拽点移动</p>

    <table>
      <thead>
        <tr>
          <th>{{ t('curves.temp_col') }}</th>
          <th>{{ t('curves.pct_col') }}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(p, i) in sortedPoints" :key="`${p.temp}-${p.pct}-${i}`">
          <td><input type="number" :value="p.temp" @change="updateRow(i, 'temp', $event.target.value)" /></td>
          <td><input type="number" :value="p.pct" @change="updateRow(i, 'pct', $event.target.value)" /></td>
          <td><button class="danger" @click="removeRow(i)">{{ t('common.delete') }}</button></td>
        </tr>
      </tbody>
    </table>
    <button @click="addRow">{{ t('curves.add_point') }}</button>
  </div>
</template>

<style scoped>
.curve-editor .meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  margin-bottom: 10px;
}
.curve-editor .meta label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text);
}
.curve-editor .meta .meta-key {
  display: inline-block;
  min-width: 56px;
  color: var(--text-dim);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  text-align: right;
}
.curve-editor .meta input,
.curve-editor .meta select {
  font-family: var(--mono);
  min-width: 160px;
}

.canvas {
  width: 100%;
  height: 520px;
  display: block;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 3px;
}
.grid line { stroke: var(--border); stroke-width: 0.6; }
.grid-minor line { stroke: var(--row-alt); stroke-width: 0.4; }
.axis-labels text {
  font-size: 11px;
  fill: var(--text-dim);
  font-family: var(--mono);
}
.axis-labels .axis-title {
  font-size: 12px;
  fill: var(--text-dim);
  font-weight: 500;
  font-family: inherit;
}
.live-overlay line { stroke: var(--warn); stroke-dasharray: 4,3; stroke-width: 1.2; }
.live-overlay circle { fill: var(--warn); stroke: var(--panel); stroke-width: 1.5; }
.live-overlay .live-label {
  font-size: 12px;
  fill: var(--warn);
  font-weight: 600;
  font-family: var(--mono);
}
.grab { cursor: grab; }
.grab:active { cursor: grabbing; }
.hint {
  color: var(--text-dim);
  font-size: 12px;
  margin: 6px 0 10px;
}
table { margin-top: 8px; }
</style>
