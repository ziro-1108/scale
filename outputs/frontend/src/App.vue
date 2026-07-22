<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import axios from 'axios'
import {
  Activity,
  AlertTriangle,
  CalendarDays,
  ClipboardList,
  Image as ImageIcon,
  RefreshCcw,
  UploadCloud,
  Wrench
} from '@lucide/vue'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const today = new Date().toISOString().slice(0, 10)
const twoWeeksAgo = new Date(Date.now() - 13 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)

const activeView = ref('dashboard')
const loading = ref(false)
const apiWarning = ref('')
const equipments = ref([])
const dashboard = ref({ range: {}, trend: [], trend_series: [], equipment_status: [] })
const filters = reactive({ start_date: twoWeeksAgo, end_date: today, status_date: today })
const issueModal = reactive({
  open: false,
  issue_id: null,
  equipment_id: null,
  start_date: today,
  end_date: today,
  issue_text: ''
})
const uploadForm = reactive({ equipment_id: '', measured_date: today, magnification: 'HIGH', files: [] })
const reviewForm = reactive({ equipment_id: '', measured_date: today, magnification: 'HIGH' })
const reviewImages = ref([])
const selectedResultIds = ref(new Set())
const reviewMessage = ref('')
const highChartRef = ref(null)
const middleChartRef = ref(null)
const chartLoadError = ref('')
const plotlyReady = reactive({ high: false, middle: false })
let plotlyLoadPromise = null

const sampleEquipments = [
  { id: 1, name: 'SCALE-A01', is_active: true },
  { id: 2, name: 'SCALE-B07', is_active: true },
  { id: 3, name: 'SCALE-C12', is_active: true },
  { id: 4, name: 'SCALE-D03', is_active: true }
]

function sampleDashboard() {
  const trend = Array.from({ length: 14 }, (_, index) => {
    const d = new Date(Date.now() - (13 - index) * 24 * 60 * 60 * 1000)
    const wave = Math.sin(index / 2.2)
    return {
      date: d.toISOString().slice(0, 10),
      high_avg_error: Number((wave * 0.42 + 0.08).toFixed(3)),
      middle_avg_error: Number((Math.cos(index / 2.7) * 0.34 - 0.05).toFixed(3)),
      high_count: 3 + (index % 3),
      middle_count: 3 + (index % 2),
      outlier_count: index === 10 ? 1 : 0
    }
  })
  return {
    range: { start_date: twoWeeksAgo, end_date: today, status_date: today },
    trend,
    trend_series: [
      {
        equipment_id: 1,
        equipment_name: 'SCALE-A01',
        magnification: 'HIGH',
        points: trend.map((row) => ({
          date: row.date,
          avg_error: row.high_avg_error,
          avg_distortion: 0.12,
          count: row.high_count,
          outlier_count: row.outlier_count
        }))
      },
      {
        equipment_id: 2,
        equipment_name: 'SCALE-B07',
        magnification: 'HIGH',
        points: trend.map((row, index) => ({
          date: row.date,
          avg_error: Number(((row.high_avg_error ?? 0) + 0.16 + Math.sin(index / 3) * 0.06).toFixed(3)),
          avg_distortion: 0.15,
          count: row.high_count,
          outlier_count: 0
        }))
      },
      {
        equipment_id: 1,
        equipment_name: 'SCALE-A01',
        magnification: 'MIDDLE',
        points: trend.map((row) => ({
          date: row.date,
          avg_error: row.middle_avg_error,
          avg_distortion: 0.11,
          count: row.middle_count,
          outlier_count: row.outlier_count
        }))
      }
    ],
    equipment_status: [
      { equipment_id: 1, equipment_name: 'SCALE-A01', high_task_count: 3, middle_task_count: 3, high_count: 3, middle_count: 3, image_registered: true, completed: true, status: 'completed', issues: [] },
      { equipment_id: 2, equipment_name: 'SCALE-B07', high_task_count: 3, middle_task_count: 3, high_count: 2, middle_count: 3, image_registered: true, completed: false, status: 'registered', issues: [] },
      { equipment_id: 3, equipment_name: 'SCALE-C12', high_task_count: 3, middle_task_count: 2, high_count: 3, middle_count: 1, image_registered: true, completed: false, status: 'issue', issues: [{ id: 9, issue_text: '렌즈 점검 진행', start_date: today, end_date: today }] },
      { equipment_id: 4, equipment_name: 'SCALE-D03', high_task_count: 0, middle_task_count: 0, high_count: 0, middle_count: 0, image_registered: false, completed: false, status: 'pending', issues: [] }
    ]
  }
}

async function fetchEquipments() {
  try {
    const response = await axios.get(`${API_BASE}/api/equipments`)
    equipments.value = response.data
  } catch {
    equipments.value = sampleEquipments
    apiWarning.value = 'API 연결 전이라 샘플 데이터로 화면을 표시하고 있습니다.'
  }
  if (!uploadForm.equipment_id && equipments.value[0]) uploadForm.equipment_id = equipments.value[0].id
  if (!reviewForm.equipment_id && equipments.value[0]) reviewForm.equipment_id = equipments.value[0].id
}

function ensureAllEquipmentRows(data) {
  const rows = data.equipment_status || []
  const existingIds = new Set(rows.map((row) => String(row.equipment_id)))
  const missingRows = equipments.value
    .filter((equipment) => !existingIds.has(String(equipment.id)))
    .map((equipment) => ({
      equipment_id: equipment.id,
      equipment_name: equipment.name,
      high_count: 0,
      middle_count: 0,
      high_task_count: 0,
      middle_task_count: 0,
      image_registered: false,
      completed: false,
      status: 'pending',
      issues: []
    }))

  return {
    ...data,
    equipment_status: [...rows, ...missingRows].sort((a, b) =>
      String(a.equipment_name).localeCompare(String(b.equipment_name), 'ko')
    )
  }
}

async function resolveEquipmentId(selectedId) {
  const selected = equipments.value.find((equipment) => String(equipment.id) === String(selectedId))
  if (!selected) return selectedId
  const response = await axios.post(`${API_BASE}/api/equipments`, {
    name: selected.name,
    is_active: selected.is_active ?? true
  })
  const realEquipment = response.data
  equipments.value = equipments.value.map((equipment) =>
    equipment.name === realEquipment.name ? realEquipment : equipment
  )
  return realEquipment.id
}

async function fetchDashboard() {
  loading.value = true
  try {
    await fetchEquipments()
    const response = await axios.get(`${API_BASE}/api/dashboard`, { params: filters })
    dashboard.value = ensureAllEquipmentRows(response.data)
    apiWarning.value = ''
  } catch {
    dashboard.value = ensureAllEquipmentRows(sampleDashboard())
    apiWarning.value = 'API 연결 전이라 샘플 데이터로 화면을 표시하고 있습니다.'
  } finally {
    loading.value = false
  }
}

function openIssueModal(row = null) {
  const existingIssue = row?.issues?.[0] || null
  issueModal.open = true
  issueModal.issue_id = existingIssue?.id || null
  issueModal.equipment_id = row?.equipment_id || equipments.value[0]?.id || null
  issueModal.start_date = existingIssue?.start_date || filters.status_date
  issueModal.end_date = existingIssue?.end_date || filters.status_date
  issueModal.issue_text = existingIssue?.issue_text || ''
}

async function saveIssue() {
  const equipmentId = await resolveEquipmentId(issueModal.equipment_id)
  const payload = {
    equipment_id: equipmentId,
    start_date: issueModal.start_date,
    end_date: issueModal.end_date,
    issue_text: issueModal.issue_text,
    status: 'open',
    created_by: 'admin'
  }
  if (issueModal.issue_id) {
    await axios.put(`${API_BASE}/api/issues/${issueModal.issue_id}`, payload)
  } else {
    await axios.post(`${API_BASE}/api/issues`, payload)
  }
  issueModal.open = false
  await fetchDashboard()
}

function onDrop(event) {
  uploadForm.files = Array.from(event.dataTransfer.files || [])
}

function onFileInput(event) {
  uploadForm.files = Array.from(event.target.files || [])
}

async function submitUpload() {
  const equipmentId = await resolveEquipmentId(uploadForm.equipment_id)
  const body = new FormData()
  body.append('equipment_id', equipmentId)
  body.append('measured_date', uploadForm.measured_date)
  body.append('magnification', uploadForm.magnification)
  uploadForm.files.forEach((file) => body.append('files', file))
  await axios.post(`${API_BASE}/api/upload/mock`, body)
  uploadForm.files = []
  await fetchDashboard()
}

async function fetchReviewImages() {
  reviewMessage.value = ''
  selectedResultIds.value = new Set()
  try {
    const response = await axios.get(`${API_BASE}/api/images`, {
      params: {
        date: reviewForm.measured_date,
        equipment_id: reviewForm.equipment_id,
        magnification: reviewForm.magnification
      }
    })
    reviewImages.value = response.data
  } catch {
    reviewImages.value = []
    reviewMessage.value = '이미지 API에 연결할 수 없습니다.'
  }
}

function toggleResult(id) {
  const next = new Set(selectedResultIds.value)
  next.has(id) ? next.delete(id) : next.add(id)
  selectedResultIds.value = next
}

async function saveOverride() {
  await axios.post(`${API_BASE}/api/calibration-overrides`, {
    equipment_id: reviewForm.equipment_id,
    measured_date: reviewForm.measured_date,
    magnification: reviewForm.magnification,
    result_ids: Array.from(selectedResultIds.value),
    note: 'Image review selection'
  })
  reviewMessage.value = '선택한 이미지 평균값을 저장했습니다.'
  await fetchDashboard()
}

const summary = computed(() => {
  const rows = dashboard.value.equipment_status || []
  return {
    total: rows.length,
    completed: rows.filter((row) => row.completed).length,
    issues: rows.filter((row) => row.issues?.length).length,
    pending: rows.filter((row) => !row.completed).length
  }
})

const fallbackChart = computed(() => {
  const rows = dashboard.value.trend || []
  const width = 820
  const height = 280
  const pad = { left: 46, right: 24, top: 20, bottom: 44 }
  const innerW = width - pad.left - pad.right
  const innerH = height - pad.top - pad.bottom
  const yMin = -1.5
  const yMax = 1.5
  const x = (i) => pad.left + (rows.length <= 1 ? 0 : (i / (rows.length - 1)) * innerW)
  const y = (value) => {
    const clamped = Math.max(yMin, Math.min(yMax, value ?? 0))
    return pad.top + ((yMax - clamped) / (yMax - yMin)) * innerH
  }
  const line = (key) =>
    rows
      .map((row, i) => (row[key] === null || row[key] === undefined ? null : `${x(i)},${y(row[key])}`))
      .filter(Boolean)
      .join(' ')
  return { rows, width, height, pad, x, y, high: line('high_avg_error'), middle: line('middle_avg_error') }
})

const chartColors = [
  '#1769e0',
  '#14a085',
  '#e85d04',
  '#7c3aed',
  '#d6336c',
  '#0f766e',
  '#64748b',
  '#b45309',
  '#2563eb',
  '#059669'
]

function aggregateFallbackSeries(valueKey) {
  const rows = dashboard.value.trend || []
  return [
    {
      equipment_name: 'Overall',
      points: rows.map((row) => ({
        date: row.date,
        avg_error: row[valueKey],
        count: row[valueKey] === null || row[valueKey] === undefined ? 0 : 1
      }))
    }
  ]
}

function buildPlotConfig(magnification, fallbackKey) {
  const sourceSeries =
    dashboard.value.trend_series?.filter((series) => series.magnification === magnification) || []
  const seriesList = sourceSeries.length ? sourceSeries : aggregateFallbackSeries(fallbackKey)
  const numericValues = seriesList
    .flatMap((series) => series.points || [])
    .map((point) => point.avg_error)
    .filter((value) => value !== null && value !== undefined)
  const maxAbs = Math.max(1.5, ...numericValues.map((value) => Math.abs(value)))
  const yLimit = Math.min(24, Math.max(1.5, Number((maxAbs * 1.12).toFixed(1))))
  const traces = seriesList.map((series, index) => {
    const color = chartColors[index % chartColors.length]
    const points = series.points || []
    return {
      name: series.equipment_name,
      x: points.map((point) => point.date),
      y: points.map((point) => point.avg_error),
      customdata: points.map((point) => point.count),
      type: 'scatter',
      mode: 'lines+markers',
      connectgaps: false,
      line: { color, width: 2.5, shape: 'spline', smoothing: 0.65 },
      marker: {
        color,
        size: 7,
        line: { color: '#ffffff', width: 1.5 }
      },
      hovertemplate: '%{fullData.name}<br>%{x}<br>Error %{y:.4f}<br>Count %{customdata}<extra></extra>'
    }
  })
  const layout = {
    autosize: true,
    height: 310,
    margin: { l: 48, r: 20, t: 12, b: 42 },
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: '#fbfdff',
    hovermode: 'x unified',
    showlegend: true,
    legend: {
      orientation: 'h',
      x: 0,
      xanchor: 'left',
      y: 1.08,
      yanchor: 'bottom',
      font: { color: '#475467', size: 11 }
    },
    xaxis: {
      type: 'date',
      tickformat: '%m-%d',
      gridcolor: '#edf2f7',
      zeroline: false,
      linecolor: '#d9e2ec',
      tickfont: { color: '#667085', size: 11 }
    },
    yaxis: {
      range: [-yLimit, yLimit],
      gridcolor: '#e8eef5',
      zeroline: true,
      zerolinecolor: '#b7c2ce',
      zerolinewidth: 1,
      linecolor: '#d9e2ec',
      tickfont: { color: '#667085', size: 11 },
      title: { text: 'Error', font: { color: '#667085', size: 12 } }
    },
    shapes: [
      {
        type: 'rect',
        xref: 'paper',
        x0: 0,
        x1: 1,
        yref: 'y',
        y0: -1,
        y1: 1,
        fillcolor: '#ecfdf6',
        opacity: 0.58,
        line: { width: 0 },
        layer: 'below'
      },
      {
        type: 'line',
        xref: 'paper',
        x0: 0,
        x1: 1,
        yref: 'y',
        y0: 1,
        y1: 1,
        line: { color: '#f59e0b', width: 1, dash: 'dot' }
      },
      {
        type: 'line',
        xref: 'paper',
        x0: 0,
        x1: 1,
        yref: 'y',
        y0: -1,
        y1: -1,
        line: { color: '#f59e0b', width: 1, dash: 'dot' }
      }
    ]
  }
  return { data: traces, layout }
}

function loadPlotly() {
  if (window.Plotly) return Promise.resolve(window.Plotly)
  if (plotlyLoadPromise) return plotlyLoadPromise
  plotlyLoadPromise = new Promise((resolve, reject) => {
    const existingScript = document.querySelector('script[data-plotly-loader="true"]')
    if (existingScript) {
      existingScript.addEventListener('load', () => resolve(window.Plotly), { once: true })
      existingScript.addEventListener('error', reject, { once: true })
      return
    }
    const script = document.createElement('script')
    script.src = '/vendor/plotly-basic.min.js'
    script.async = true
    script.dataset.plotlyLoader = 'true'
    script.onload = () => resolve(window.Plotly)
    script.onerror = () => reject(new Error('Plotly script load failed'))
    document.head.appendChild(script)
  })
  return plotlyLoadPromise
}

async function renderCharts() {
  if (activeView.value !== 'dashboard') return
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 500))
  let plotly
  try {
    plotly = await loadPlotly()
    chartLoadError.value = ''
  } catch {
    chartLoadError.value = '그래프 라이브러리를 불러오지 못했습니다.'
    return
  }
  if (!plotly) return
  const options = { displayModeBar: false, responsive: true }
  if (highChartRef.value) {
    const high = buildPlotConfig('HIGH', 'high_avg_error')
    await plotly.react(highChartRef.value, high.data, high.layout, options)
    plotlyReady.high = true
  }
  if (middleChartRef.value) {
    const middle = buildPlotConfig('MIDDLE', 'middle_avg_error')
    await plotly.react(middleChartRef.value, middle.data, middle.layout, options)
    plotlyReady.middle = true
  }
}

watch(
  () => [dashboard.value.trend, dashboard.value.trend_series, activeView.value],
  () => renderCharts(),
  { deep: true }
)

onMounted(async () => {
  await fetchEquipments()
  await fetchDashboard()
  await renderCharts()
})

onBeforeUnmount(() => {
  if (window.Plotly && highChartRef.value) window.Plotly.purge(highChartRef.value)
  if (window.Plotly && middleChartRef.value) window.Plotly.purge(middleChartRef.value)
})
</script>

<template>
  <div class="shell">
    <header class="app-header">
      <div class="brand">
        <div class="brand-mark"><Activity :size="24" /></div>
        <div>
          <strong>SCALE</strong>
          <span>Calibration Monitor</span>
        </div>
      </div>
      <div class="header-meta">
        <span>설비 Calibration 통합 모니터링</span>
        <button class="icon-button" title="새로고침" @click="fetchDashboard">
          <RefreshCcw :size="18" />
        </button>
      </div>
    </header>

    <nav class="nav-bar">
      <button :class="{ active: activeView === 'dashboard' }" @click="activeView = 'dashboard'">
        <ClipboardList :size="18" /> Dashboard
      </button>
      <button :class="{ active: activeView === 'upload' }" @click="activeView = 'upload'">
        <UploadCloud :size="18" /> Upload
      </button>
      <button :class="{ active: activeView === 'review' }" @click="activeView = 'review'; fetchReviewImages()">
        <ImageIcon :size="18" /> Image Review
      </button>
    </nav>

    <main class="content">
      <header v-if="activeView !== 'dashboard'" class="topbar">
        <div>
          <h1>{{ activeView === 'upload' ? '관리자 이미지 업로드' : '이미지 리뷰' }}</h1>
        </div>
      </header>

      <p v-if="apiWarning" class="notice">{{ apiWarning }}</p>

      <section v-if="activeView === 'dashboard'" class="dashboard-grid">
        <div class="toolbar wide">
          <label>
            시작일
            <input v-model="filters.start_date" type="date" />
          </label>
          <label>
            종료일
            <input v-model="filters.end_date" type="date" />
          </label>
          <label>
            점검 기준일
            <input v-model="filters.status_date" type="date" />
          </label>
          <button class="primary" @click="fetchDashboard"><CalendarDays :size="17" /> 조회</button>
          <button class="secondary" @click="openIssueModal()"><Wrench :size="17" /> Issue 등록</button>
        </div>

        <div class="metrics wide">
          <div><span>설비</span><strong>{{ summary.total }}</strong></div>
          <div><span>완료</span><strong>{{ summary.completed }}</strong></div>
          <div><span>미완료</span><strong>{{ summary.pending }}</strong></div>
          <div><span>Issue</span><strong>{{ summary.issues }}</strong></div>
        </div>

        <div class="chart-stack">
          <p v-if="chartLoadError" class="notice">{{ chartLoadError }}</p>
          <section class="panel chart-panel">
            <div class="panel-head">
              <div>
                <h2>고배율 Calibration 현황</h2>
              </div>
            </div>
            <div ref="highChartRef" class="plotly-chart">
              <svg v-if="!plotlyReady.high" class="fallback-chart" :viewBox="`0 0 ${fallbackChart.width} ${fallbackChart.height}`" role="img">
                <rect :x="fallbackChart.pad.left" :y="fallbackChart.y(1)" :width="fallbackChart.width - fallbackChart.pad.left - fallbackChart.pad.right" :height="fallbackChart.y(-1) - fallbackChart.y(1)" class="normal-band" />
                <line :x1="fallbackChart.pad.left" :x2="fallbackChart.width - fallbackChart.pad.right" :y1="fallbackChart.y(1)" :y2="fallbackChart.y(1)" class="limit" />
                <line :x1="fallbackChart.pad.left" :x2="fallbackChart.width - fallbackChart.pad.right" :y1="fallbackChart.y(-1)" :y2="fallbackChart.y(-1)" class="limit" />
                <line :x1="fallbackChart.pad.left" :x2="fallbackChart.width - fallbackChart.pad.right" :y1="fallbackChart.y(0)" :y2="fallbackChart.y(0)" class="zero" />
                <polyline :points="fallbackChart.high" class="line high-line" />
                <g v-for="(row, i) in fallbackChart.rows" :key="`high-fallback-${row.date}`">
                  <circle v-if="row.high_avg_error !== null" :cx="fallbackChart.x(i)" :cy="fallbackChart.y(row.high_avg_error)" r="4" class="dot high-dot" />
                  <text v-if="i % 2 === 0 || fallbackChart.rows.length < 10" :x="fallbackChart.x(i)" y="264" text-anchor="middle">{{ row.date.slice(5) }}</text>
                </g>
                <text x="8" :y="fallbackChart.y(1) + 4">+1</text>
                <text x="8" :y="fallbackChart.y(0) + 4">0</text>
                <text x="8" :y="fallbackChart.y(-1) + 4">-1</text>
              </svg>
            </div>
          </section>

          <section class="panel chart-panel">
            <div class="panel-head">
              <div>
                <h2>중배율 Calibration 현황</h2>
              </div>
            </div>
            <div ref="middleChartRef" class="plotly-chart">
              <svg v-if="!plotlyReady.middle" class="fallback-chart" :viewBox="`0 0 ${fallbackChart.width} ${fallbackChart.height}`" role="img">
                <rect :x="fallbackChart.pad.left" :y="fallbackChart.y(1)" :width="fallbackChart.width - fallbackChart.pad.left - fallbackChart.pad.right" :height="fallbackChart.y(-1) - fallbackChart.y(1)" class="normal-band" />
                <line :x1="fallbackChart.pad.left" :x2="fallbackChart.width - fallbackChart.pad.right" :y1="fallbackChart.y(1)" :y2="fallbackChart.y(1)" class="limit" />
                <line :x1="fallbackChart.pad.left" :x2="fallbackChart.width - fallbackChart.pad.right" :y1="fallbackChart.y(-1)" :y2="fallbackChart.y(-1)" class="limit" />
                <line :x1="fallbackChart.pad.left" :x2="fallbackChart.width - fallbackChart.pad.right" :y1="fallbackChart.y(0)" :y2="fallbackChart.y(0)" class="zero" />
                <polyline :points="fallbackChart.middle" class="line middle-line" />
                <g v-for="(row, i) in fallbackChart.rows" :key="`middle-fallback-${row.date}`">
                  <circle v-if="row.middle_avg_error !== null" :cx="fallbackChart.x(i)" :cy="fallbackChart.y(row.middle_avg_error)" r="4" class="dot middle-dot" />
                  <text v-if="i % 2 === 0 || fallbackChart.rows.length < 10" :x="fallbackChart.x(i)" y="264" text-anchor="middle">{{ row.date.slice(5) }}</text>
                </g>
                <text x="8" :y="fallbackChart.y(1) + 4">+1</text>
                <text x="8" :y="fallbackChart.y(0) + 4">0</text>
                <text x="8" :y="fallbackChart.y(-1) + 4">-1</text>
              </svg>
            </div>
          </section>
        </div>

        <section class="panel status-panel">
          <div class="panel-head compact status-head">
            <h2>설비 점검 현황</h2>
            <p>{{ filters.status_date }} 기준</p>
          </div>
          <div class="status-table">
            <div class="status-row header">
              <span>설비</span><span>H Mag.</span><span>M Mag.</span><span>상태</span>
            </div>
            <div v-for="row in dashboard.equipment_status" :key="row.equipment_id" class="status-row">
              <strong>{{ row.equipment_name }}</strong>
              <span :class="['ox-mark', { ok: row.high_task_count >= 3 }]">
                {{ row.high_task_count >= 3 ? 'O' : 'X' }}
              </span>
              <span :class="['ox-mark', { ok: row.middle_task_count >= 3 }]">
                {{ row.middle_task_count >= 3 ? 'O' : 'X' }}
              </span>
              <button
                v-if="row.issues?.length"
                class="issue-status"
                :title="row.issues[0].issue_text"
                @click="openIssueModal(row)"
              >
                {{ row.issues[0].issue_text }}
              </button>
              <span v-else class="status-empty"></span>
            </div>
          </div>
        </section>
      </section>

      <section v-if="activeView === 'upload'" class="page-panel">
        <div class="panel-head">
          <div>
            <h2>관리자 이미지 업로드</h2>
            <p>잘못 촬영된 이미지를 다시 등록하기 위한 mock 측정 요청입니다.</p>
          </div>
        </div>
        <div class="form-grid">
          <label>설비<select v-model="uploadForm.equipment_id"><option v-for="eq in equipments" :key="eq.id" :value="eq.id">{{ eq.name }}</option></select></label>
          <label>측정일<input v-model="uploadForm.measured_date" type="date" /></label>
          <label>배율<select v-model="uploadForm.magnification"><option>HIGH</option><option>MIDDLE</option></select></label>
        </div>
        <label class="dropzone" @drop.prevent="onDrop" @dragover.prevent>
          <UploadCloud :size="34" />
          <strong>이미지를 드래그하거나 클릭해서 선택</strong>
          <span>{{ uploadForm.files.length ? `${uploadForm.files.length}개 파일 선택됨` : 'JPG/PNG 파일을 업로드하세요.' }}</span>
          <input type="file" multiple accept="image/*" @change="onFileInput" />
        </label>
        <button class="primary" :disabled="!uploadForm.files.length" @click="submitUpload">측정 Queue 등록</button>
      </section>

      <section v-if="activeView === 'review'" class="page-panel">
        <div class="panel-head">
          <div>
            <h2>이미지 리뷰 및 Calibration 선택</h2>
            <p>특정 일자와 설비의 이미지를 선택해 평균값을 저장합니다.</p>
          </div>
        </div>
        <div class="toolbar">
          <label>설비<select v-model="reviewForm.equipment_id"><option v-for="eq in equipments" :key="eq.id" :value="eq.id">{{ eq.name }}</option></select></label>
          <label>일자<input v-model="reviewForm.measured_date" type="date" /></label>
          <label>배율<select v-model="reviewForm.magnification"><option>HIGH</option><option>MIDDLE</option></select></label>
          <button class="secondary" @click="fetchReviewImages"><ImageIcon :size="17" /> 이미지 조회</button>
        </div>
        <p v-if="reviewMessage" class="notice">{{ reviewMessage }}</p>
        <div class="image-grid">
          <button
            v-for="image in reviewImages"
            :key="image.id"
            :class="['image-tile', { selected: selectedResultIds.has(image.result_id) }]"
            :disabled="!image.result_id"
            @click="toggleResult(image.result_id)"
          >
            <img v-if="image.thumbnail_url" :src="`${API_BASE}${image.thumbnail_url}`" alt="" />
            <div v-else class="empty-thumb"><ImageIcon :size="30" /></div>
            <strong>Error {{ image.error_value ?? '-' }}</strong>
            <span>Distortion {{ image.distortion_value ?? '-' }}</span>
          </button>
        </div>
        <button class="primary" :disabled="!selectedResultIds.size" @click="saveOverride">
          선택 평균값 저장
        </button>
      </section>
    </main>

    <div v-if="issueModal.open" class="modal-backdrop" @click.self="issueModal.open = false">
      <form class="modal" @submit.prevent="saveIssue">
        <h2>{{ issueModal.issue_id ? '설비 Issue 수정' : '설비 Issue 등록' }}</h2>
        <label>설비<select v-model="issueModal.equipment_id"><option v-for="eq in equipments" :key="eq.id" :value="eq.id">{{ eq.name }}</option></select></label>
        <div class="form-grid two">
          <label>시작일<input v-model="issueModal.start_date" type="date" /></label>
          <label>종료일<input v-model="issueModal.end_date" type="date" /></label>
        </div>
        <label>Issue<textarea v-model="issueModal.issue_text" required rows="5" placeholder="점검, 촬영 불량, 설비 고장 내용을 입력"></textarea></label>
        <div class="modal-actions">
          <button type="button" class="secondary" @click="issueModal.open = false">취소</button>
          <button class="primary" type="submit">{{ issueModal.issue_id ? '수정' : '저장' }}</button>
        </div>
      </form>
    </div>

    <footer class="app-footer">분석기술팀 시스템/자동화</footer>
  </div>
</template>
