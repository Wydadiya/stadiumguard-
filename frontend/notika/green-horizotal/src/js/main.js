/**
 * StadiumGuard — Vite entry (Bootstrap + app SCSS only)
 * Multi-stream dashboard with MJPEG streaming from backend
 */

import 'bootstrap/dist/css/bootstrap.min.css'

import { library, dom } from '@fortawesome/fontawesome-svg-core'
import {
  faVideo,
  faUsers,
  faPersonFalling,
  faWaveSquare,
  faVolumeHigh,
  faSmog,
  faShieldHalved,
  faListUl,
  faPlay,
  faPause,
  faTrash
} from '@fortawesome/free-solid-svg-icons'

library.add(faVideo, faUsers, faPersonFalling, faWaveSquare, faVolumeHigh, faSmog, faShieldHalved, faListUl, faPlay, faPause, faTrash)
dom.watch()

import '../css/modern.scss'

import * as bootstrap from 'bootstrap'
import { NotikaUI } from './modules/ui.js'
import { DataSimulator } from './modules/simulator.js'
import { BackendConnector } from './modules/backend.js'
import { MiniChart } from './modules/charts.js'

window.bootstrap = bootstrap

// ═══════════════════════════════════════════════════════════════
// STREAM MANAGER — Handles MJPEG streams from backend
// ═══════════════════════════════════════════════════════════════
class StreamManager {
  constructor(baseUrl = 'http://localhost:5000') {
    this.baseUrl = baseUrl
    this.streams = {
      lab1: { img: null, dot: null, placeholder: null, connected: false },
      lab2: { img: null, dot: null, placeholder: null, connected: false },
      lab3: { img: null, dot: null, placeholder: null, connected: false }
    }
    this.isConnected = false
    this.reconnectTimers = {}
  }

  init() {
    for (const labId of ['lab1', 'lab2', 'lab3']) {
      this.streams[labId].img = document.getElementById(`stream-${labId}`)
      this.streams[labId].dot = document.getElementById(`dot-${labId}`)
      this.streams[labId].placeholder = document.getElementById(`placeholder-${labId}`)
    }
  }

  connectAll() {
    this.isConnected = true
    for (const labId of ['lab1', 'lab2', 'lab3']) {
      this.connectStream(labId)
    }
  }

  disconnectAll() {
    this.isConnected = false
    for (const labId of ['lab1', 'lab2', 'lab3']) {
      this.disconnectStream(labId)
    }
  }

  connectStream(labId) {
    const stream = this.streams[labId]
    if (!stream.img) return

    const streamUrl = `${this.baseUrl}/api/stream/${labId}?t=${Date.now()}`

    // Set up event handlers
    stream.img.onload = () => {
      // Image loaded successfully — stream is active
      if (!stream.connected) {
        stream.connected = true
        stream.img.classList.add('active')
        if (stream.placeholder) stream.placeholder.classList.add('hidden')
        if (stream.dot) {
          stream.dot.classList.add('connected')
          stream.dot.classList.remove('error')
        }
      }
    }

    stream.img.onerror = () => {
      stream.connected = false
      stream.img.classList.remove('active')
      if (stream.placeholder) {
        stream.placeholder.classList.remove('hidden')
        const statusEl = stream.placeholder.querySelector('.sg-stream-placeholder-status')
        if (statusEl) statusEl.textContent = 'Connection lost — retrying…'
      }
      if (stream.dot) {
        stream.dot.classList.remove('connected')
        stream.dot.classList.add('error')
      }

      // Auto-reconnect after 3s
      if (this.isConnected) {
        if (this.reconnectTimers[labId]) clearTimeout(this.reconnectTimers[labId])
        this.reconnectTimers[labId] = setTimeout(() => {
          if (this.isConnected) {
            this.connectStream(labId)
          }
        }, 3000)
      }
    }

    // Start streaming
    stream.img.src = streamUrl

    // Update placeholder
    if (stream.placeholder) {
      const statusEl = stream.placeholder.querySelector('.sg-stream-placeholder-status')
      if (statusEl) statusEl.textContent = 'Connecting…'
    }
  }

  disconnectStream(labId) {
    const stream = this.streams[labId]
    if (!stream.img) return

    // Clear reconnect timer
    if (this.reconnectTimers[labId]) {
      clearTimeout(this.reconnectTimers[labId])
      delete this.reconnectTimers[labId]
    }

    // Stop the stream
    stream.img.src = ''
    stream.img.onload = null
    stream.img.onerror = null
    stream.connected = false

    stream.img.classList.remove('active')
    if (stream.placeholder) {
      stream.placeholder.classList.remove('hidden')
      const statusEl = stream.placeholder.querySelector('.sg-stream-placeholder-status')
      if (statusEl) statusEl.textContent = 'Awaiting connection…'
    }
    if (stream.dot) {
      stream.dot.classList.remove('connected', 'error')
    }
  }

  getStatus() {
    return {
      lab1: this.streams.lab1.connected,
      lab2: this.streams.lab2.connected,
      lab3: this.streams.lab3.connected
    }
  }
}


// ═══════════════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════════════
class StadiumGuardApp {
  constructor() {
    this.ui = new NotikaUI()
    this.simulator = new DataSimulator()
    this.backend = new BackendConnector('http://localhost:5000')
    this.streamManager = new StreamManager('http://localhost:5000')
    this.charts = {}
    this.isSimulating = false
    this.streamsActive = false
    this.useBackend = false
    this.lastAlertLevel = 'Normal'
    this.lastAudioLevel = null
    this.lastSmokeLevel = null
    this.init()
  }

  async init() {
    try {
      await this.ui.init()
      this.streamManager.init()
      this.setupModernFeatures()
      this.setupCharts()
      this.setupControls()
      this.setupBackend()
      this.setupStreamControls()

      // Check if backend is available
      const health = await this.backend.checkHealth()
      if (health.status === 'ok') {
        this.updateSystemStatus('Operational', true)
        this.ui.showSuccess('Backend API connected! Click "Connect Streams" to start.')
        this.useBackend = true
      } else {
        this.updateSystemStatus('Offline', false)
        this.ui.showInfo('Backend offline. Using simulator mode.')
        this.useBackend = false
      }
    } catch (error) {
      console.error('StadiumGuard init error:', error)
    }
  }

  setupModernFeatures() {
    this.removeAllScrollbarRules()
    this.addPulseAnimation()
  }

  setupCharts() {
    // Person count chart
    this.charts.person = new MiniChart('person-chart', {
      maxDataPoints: 30,
      color: '#3ecf8e',
      fillColor: 'rgba(62, 207, 142, 0.15)',
      maxValue: 500
    })

    // Threat score chart
    this.charts.threat = new MiniChart('threat-chart', {
      maxDataPoints: 30,
      color: '#e8a54b',
      fillColor: 'rgba(232, 165, 75, 0.15)',
      maxValue: 100
    })

    // Update charts when data changes
    setInterval(() => {
      if (this.isSimulating) {
        const data = this.simulator.getData()
        this.charts.person.addDataPoint(data.personCount)
        this.charts.threat.addDataPoint(data.threatScore)
      }
    }, 1000)
  }

  setupStreamControls() {
    const toggleBtn = document.getElementById('toggle-streams')
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        this.toggleStreams(toggleBtn)
      })
    }
  }

  toggleStreams(button) {
    this.streamsActive = !this.streamsActive

    if (this.streamsActive) {
      this.streamManager.connectAll()

      // Also start backend data polling
      if (this.useBackend) {
        this.backend.startPolling(500)
      }

      button.innerHTML = '<i class="fa-solid fa-pause"></i> Disconnect'
      button.classList.remove('btn-outline-success')
      button.classList.add('btn-outline-danger')
      this.addEventToLog('🎬 Streams connected — receiving live video', 'success')
      this.ui.showSuccess('Streams connected!')
    } else {
      this.streamManager.disconnectAll()

      if (this.useBackend) {
        this.backend.stopPolling()
      }

      button.innerHTML = '<i class="fa-solid fa-play"></i> Connect Streams'
      button.classList.remove('btn-outline-danger')
      button.classList.add('btn-outline-success')
      this.addEventToLog('⏸️ Streams disconnected', 'info')
      this.ui.showInfo('Streams disconnected')
    }
  }

  setupControls() {
    const toggleBtn = document.getElementById('toggle-simulation')
    const clearBtn = document.getElementById('clear-log')

    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        this.toggleSimulation(toggleBtn)
      })
    }

    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        this.clearEventLog()
      })
    }
  }

  toggleSimulation(button) {
    this.isSimulating = !this.isSimulating

    if (this.isSimulating) {
      this.simulator.start()
      button.innerHTML = '<i class="fa-solid fa-pause"></i> Stop Demo'
      button.classList.remove('btn-outline-success')
      button.classList.add('btn-outline-danger')
      this.ui.showSuccess('Simulation started')
    } else {
      this.simulator.stop()
      button.innerHTML = '<i class="fa-solid fa-play"></i> Start Demo'
      button.classList.remove('btn-outline-danger')
      button.classList.add('btn-outline-success')
      this.ui.showInfo('Simulation stopped')
    }
  }

  setupBackend() {
    // Callback when data arrives from backend
    this.backend.onData((data) => {
      this.updateDashboardFromBackend(data)
    })

    // Callback on error
    this.backend.onError((error) => {
      this.updateSystemStatus('Offline', false)
    })

    // Callback on connect
    this.backend.onConnect(() => {
      this.updateSystemStatus('Operational', true)
      this.addEventToLog('✅ Backend API connected', 'success')
    })

    // Callback on disconnect
    this.backend.onDisconnect((error) => {
      this.updateSystemStatus('Offline', false)
      this.addEventToLog('❌ Backend connection lost', 'danger')
    })
  }

  updateDashboardFromBackend(data) {
    // Get individual lab data if available
    const individual = data._individual || {}
    
    // ── Person count (from lab1 raw details) ──────────────────────
    const personRaw = individual.person || {}
    const personCount = personRaw?.details?.person_count ?? Math.round((data.scores?.person || 0) / 5)
    this.updateElement('person-count', personCount)
    this.charts.person.addDataPoint(personCount)

    // ── Threat score ──────────────────────────────────────────────
    const threatScore = Math.round(data.final_score || 0)
    this.updateElement('threat-score', threatScore, '/100')
    this.charts.threat.addDataPoint(threatScore)

    // ── Alert level ───────────────────────────────────────────────
    this.updateAlertLevel(data.level || 'LOW')

    // ── Fall status (from lab2) ───────────────────────────────────
    const fallScore = data.scores?.fall || 0
    const fallRaw = individual.fall || {}
    const statuses = fallRaw?.details?.statuses || data.raw?.fall?.statuses || {}
    
    // Check for any non-STANDING person
    const fallenPersons = Object.entries(statuses)
      .filter(([id, status]) => status !== 'STANDING')
    
    const hasFall = fallScore > 60 || fallenPersons.length > 0
    const fallStatus = hasFall ? 'DETECTED!' : 'Clear'
    const fallElement = document.getElementById('fall-status')
    if (fallElement) {
      fallElement.textContent = fallStatus
      fallElement.style.color = hasFall ? '#e85d5d' : ''
      fallElement.style.fontWeight = hasFall ? '600' : ''
    }

    // ── Motion level (from lab3) ──────────────────────────────────
    const motionScore = data.scores?.motion || 0
    const motionRaw = individual.motion || {}
    const motionLabel = motionRaw?.details?.label || null
    
    let motionLevel = 'Low'
    if (motionLabel) {
      // Use the actual label from lab3 if available
      const labelMap = {
        'CALM': 'Low',
        'LEARNING': 'Learning…',
        'CELEBRATION': 'Celebration',
        'FIGHT': 'FIGHT!',
        'STAMPEDE': 'STAMPEDE!'
      }
      motionLevel = labelMap[motionLabel] || motionLabel
    } else {
      // Fallback to score-based level
      if (motionScore > 70) motionLevel = 'Very High'
      else if (motionScore > 50) motionLevel = 'High'
      else if (motionScore > 30) motionLevel = 'Medium'
    }
    
    const motionElement = document.getElementById('motion-level')
    if (motionElement) {
      motionElement.textContent = motionLevel
      const colors = {
        'FIGHT!': '#e85d5d',
        'STAMPEDE!': '#e85d5d',
        'Very High': '#e85d5d',
        'High': '#e8a54b',
        'Medium': '#7eb8ff',
        'Celebration': '#7eb8ff',
        'Low': '#3ecf8e',
        'Learning…': '#8b909a'
      }
      motionElement.style.color = colors[motionLevel] || '#3ecf8e'
    }

    // ── Audio activity (from pc_mic) ──────────────────────────────
    const audioScore = data.scores?.audio || 0
    const audioRaw = individual.audio || {}
    const audioLabelRaw = audioRaw?.details?.label || data.raw?.audio?.label || null
    const normalizedAudioLabel = audioLabelRaw ? String(audioLabelRaw).toLowerCase() : null
    const audioTs = audioRaw?.timestamp || 0
    const audioAgeSec = audioTs ? (Date.now() / 1000 - audioTs) : Number.POSITIVE_INFINITY
    const audioIsStale = audioAgeSec > 5
    const audioWarmRemaining = Number(audioRaw?.details?.remaining_s ?? 0)
    const audioIsWarming = audioRaw?.details?.status === 'warming_up'

    let audioLevel = 'Unknown'
    if (audioIsWarming) {
      audioLevel = 'Warming…'
    } else if (normalizedAudioLabel) {
      const audioLabelMap = {
        silence: 'Silence',
        'chants supportaires': 'Chants',
        bagarre: 'Bagarre',
        bombes: 'Bombes'
      }
      audioLevel = audioLabelMap[normalizedAudioLabel] || audioLabelRaw
    } else {
      if (audioScore >= 85) audioLevel = 'Bombes'
      else if (audioScore >= 60) audioLevel = 'Bagarre'
      else if (audioScore >= 15) audioLevel = 'Chants'
      else audioLevel = 'Silence'
    }

    const audioElement = document.getElementById('audio-level')
    if (audioElement) {
      audioElement.textContent = audioLevel
      const audioColors = {
        Bombes: '#e85d5d',
        Bagarre: '#e8a54b',
        Chants: '#7eb8ff',
        Silence: '#3ecf8e',
        'Warming…': '#8b909a',
        Unknown: '#8b909a'
      }
      audioElement.style.color = audioColors[audioLevel] || '#8b909a'
    }

    const audioSyncElement = document.getElementById('audio-sync-status')
    if (audioSyncElement) {
      if (audioIsWarming) {
        audioSyncElement.textContent = `Warming up (${Math.ceil(audioWarmRemaining)}s)`
        audioSyncElement.style.color = '#8b909a'
      } else if (audioIsStale) {
        audioSyncElement.textContent = `Stale (${Math.round(audioAgeSec)}s old)`
        audioSyncElement.style.color = '#e8a54b'
      } else {
        audioSyncElement.textContent = 'Live'
        audioSyncElement.style.color = '#3ecf8e'
      }
    }

    // ── Smoke detection (from backend smoke endpoint) ─────────────
    const smokeRaw = individual.smoke || {}
    const smokeScore = data.scores?.smoke ?? smokeRaw?.score ?? 0
    const smokeDetectedRaw = Boolean(smokeRaw?.details?.detected) || smokeScore >= 60
    const smokeTs = smokeRaw?.timestamp || 0
    const smokeAgeSec = smokeTs ? (Date.now() / 1000 - smokeTs) : Number.POSITIVE_INFINITY
    const smokeIsStale = smokeAgeSec > 5

    // Si les données fumée sont stale, on n'affiche pas "Detected" en persistant.
    const smokeDetected = smokeDetectedRaw && !smokeIsStale
    const smokeLevel = smokeDetected ? 'Detected' : (smokeTs ? 'Clear' : 'Unknown')
    const smokeElement = document.getElementById('smoke-level')
    if (smokeElement) {
      smokeElement.textContent = smokeLevel
      const smokeColors = {
        Detected: '#e85d5d',
        Clear: '#3ecf8e',
        Unknown: '#8b909a'
      }
      smokeElement.style.color = smokeColors[smokeLevel] || '#8b909a'
    }

    const smokeSyncElement = document.getElementById('smoke-sync-status')
    if (smokeSyncElement) {
      if (!smokeTs) {
        smokeSyncElement.textContent = 'No backend data'
        smokeSyncElement.style.color = '#8b909a'
      } else if (smokeIsStale) {
        smokeSyncElement.textContent = `Stale (${Math.round(smokeAgeSec)}s old)`
        smokeSyncElement.style.color = '#e8a54b'
      } else {
        smokeSyncElement.textContent = 'Live'
        smokeSyncElement.style.color = '#3ecf8e'
      }
    }

    // ── Alert level change events ─────────────────────────────────
    if (data.level !== this.lastAlertLevel) {
      const levelMessages = {
        'CRITICAL': '🚨 CRITICAL ALERT - Immediate intervention required!',
        'HIGH': '⚠️ HIGH alert level detected',
        'MEDIUM': '⚠️ Alert level elevated to MEDIUM',
        'LOW': 'ℹ️ Alert level returned to LOW'
      }
      
      const message = levelMessages[data.level] || 'Alert level changed'
      const type = data.level === 'CRITICAL' ? 'danger' : data.level === 'HIGH' ? 'warning' : 'info'
      this.addEventToLog(message, type)
      
      this.lastAlertLevel = data.level
    }

    // ── Fall detection events ─────────────────────────────────────
    if (fallenPersons.length > 0) {
      const fallenStr = fallenPersons
        .map(([id, status]) => `Person ${id}: ${status}`)
        .join(', ')
      this.addEventToLog(`⚠️ Fall detected: ${fallenStr}`, 'warning')
    }

    // ── Fight/Stampede events ─────────────────────────────────────
    if (motionLabel === 'FIGHT') {
      this.addEventToLog('🥊 FIGHT detected — localized violent motion!', 'danger')
    } else if (motionLabel === 'STAMPEDE') {
      this.addEventToLog('🏃 STAMPEDE detected — mass directional movement!', 'danger')
    }

    // ── Audio critical events ──────────────────────────────────────
    if (audioLevel !== this.lastAudioLevel) {
      if (audioLevel === 'Bombes') {
        this.addEventToLog('💣 Audio critical pattern detected (bombes)', 'danger')
      } else if (audioLevel === 'Bagarre') {
        this.addEventToLog('⚠️ Audio anomaly detected (bagarre)', 'warning')
      }
      this.lastAudioLevel = audioLevel
    }

    if (smokeLevel !== this.lastSmokeLevel) {
      if (smokeLevel === 'Detected') {
        this.addEventToLog('🌫️ Smoke detected by backend module', 'danger')
      } else if (smokeLevel === 'Clear') {
        this.addEventToLog('✅ Smoke status returned to clear', 'success')
      }
      this.lastSmokeLevel = smokeLevel
    }
  }

  updateElement(id, value, suffix = '') {
    const element = document.getElementById(id)
    if (element) {
      element.innerHTML = `${value}<span class="sg-metric-suffix">${suffix}</span>`
    }
  }

  updateAlertLevel(level) {
    const badge = document.getElementById('alert-level')
    if (!badge) return

    badge.classList.remove('sg-badge--warn', 'sg-badge--danger')

    const levelMap = {
      'CRITICAL': { text: 'Critical', class: 'sg-badge--danger' },
      'HIGH': { text: 'High', class: 'sg-badge--danger' },
      'MEDIUM': { text: 'Elevated', class: 'sg-badge--warn' },
      'LOW': { text: 'Normal', class: '' }
    }

    const config = levelMap[level] || levelMap['LOW']
    badge.textContent = config.text
    if (config.class) {
      badge.classList.add(config.class)
    }
  }

  updateSystemStatus(status, isOnline) {
    const statusElement = document.getElementById('system-status')
    if (statusElement) {
      statusElement.textContent = status
    }

    const dot = document.querySelector('.sg-dot')
    if (dot) {
      dot.style.background = isOnline ? '#3ecf8e' : '#8b909a'
    }
  }

  addEventToLog(message, type = 'info') {
    const log = document.getElementById('event-log')
    if (!log) return

    const ul = log.querySelector('ul')
    if (!ul) return

    const time = new Date().toLocaleTimeString('en-US', { hour12: false })
    const li = document.createElement('li')

    const colors = {
      'danger': '#e85d5d',
      'warning': '#e8a54b',
      'success': '#3ecf8e',
      'info': '#8b909a'
    }

    const color = colors[type] || colors['info']
    li.innerHTML = `<span style="color: ${color}">[${time}]</span> ${message}`
    li.style.opacity = '0'
    li.style.transform = 'translateX(-10px)'
    li.style.transition = 'opacity 0.3s ease, transform 0.3s ease'

    ul.insertBefore(li, ul.firstChild)

    setTimeout(() => {
      li.style.opacity = '1'
      li.style.transform = 'translateX(0)'
    }, 10)

    // Keep only last 20 events
    while (ul.children.length > 20) {
      ul.removeChild(ul.lastChild)
    }
  }

  clearEventLog() {
    const log = document.getElementById('event-log')
    if (log) {
      const ul = log.querySelector('ul')
      if (ul) {
        ul.innerHTML = '<li><span class="text-secondary">[--:--:--]</span> Event log cleared.</li>'
        this.ui.showInfo('Event log cleared')
      }
    }
  }

  addPulseAnimation() {
    const dot = document.querySelector('.sg-dot')
    if (dot) {
      dot.style.animation = 'pulse 2s ease-in-out infinite'
    }
  }

  removeAllScrollbarRules() {
    const stylesheets = document.styleSheets
    for (let i = 0; i < stylesheets.length; i++) {
      const stylesheet = stylesheets[i]
      try {
        const rules = stylesheet.cssRules || stylesheet.rules
        if (rules) {
          for (let j = rules.length - 1; j >= 0; j--) {
            const rule = rules[j]
            if (
              rule.selectorText &&
              (rule.selectorText.includes('::-webkit-scrollbar') ||
                (rule.selectorText.includes('scrollbar') &&
                  rule.style &&
                  rule.style.display === 'none'))
            ) {
              try {
                stylesheet.deleteRule(j)
              } catch {
                /* ignore */
              }
            }
          }
        }
      } catch {
        /* CORS */
      }
    }
  }
}

if (!document.documentElement.hasAttribute('data-page-module')) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      window.StadiumGuard = new StadiumGuardApp()
    })
  } else {
    window.StadiumGuard = new StadiumGuardApp()
  }
}

export { StadiumGuardApp }
