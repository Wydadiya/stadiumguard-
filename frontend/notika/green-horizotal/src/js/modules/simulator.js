/**
 * Data Simulator Module
 * Simulates real-time AI monitoring data for demo purposes
 */

export class DataSimulator {
  constructor() {
    this.isRunning = false
    this.intervals = []
    this.personCount = 0
    this.threatScore = 0
    this.motionLevel = 'Low'
    this.fallDetected = false
    this.eventHistory = []
  }

  start() {
    if (this.isRunning) return
    this.isRunning = true
    
    // Update video status
    this.updateVideoStatus(true)
    
    // Simulate person count changes
    this.intervals.push(setInterval(() => {
      this.updatePersonCount()
    }, 3000))
    
    // Simulate threat score fluctuations
    this.intervals.push(setInterval(() => {
      this.updateThreatScore()
    }, 2000))
    
    // Simulate motion detection
    this.intervals.push(setInterval(() => {
      this.updateMotionLevel()
    }, 4000))
    
    // Simulate fall detection (rare event)
    this.intervals.push(setInterval(() => {
      this.checkFallDetection()
    }, 8000))
    
    // Add random events
    this.intervals.push(setInterval(() => {
      this.generateRandomEvent()
    }, 6000))
  }

  stop() {
    this.isRunning = false
    this.intervals.forEach(interval => clearInterval(interval))
    this.intervals = []
    this.updateVideoStatus(false)
  }

  updateVideoStatus(active) {
    const statusDot = document.querySelector('.sg-status-dot')
    const statusText = document.querySelector('.sg-status-text')
    
    if (statusDot && statusText) {
      if (active) {
        statusDot.style.background = '#3ecf8e'
        statusText.textContent = 'Stream active'
      } else {
        statusDot.style.background = '#8b909a'
        statusText.textContent = 'Awaiting stream'
      }
    }
  }

  updatePersonCount() {
    const change = Math.floor(Math.random() * 10) - 4
    this.personCount = Math.max(0, Math.min(500, this.personCount + change))
    
    const element = document.getElementById('person-count')
    if (element) {
      this.animateNumber(element, parseInt(element.textContent) || 0, this.personCount)
    }
  }

  updateThreatScore() {
    const change = Math.floor(Math.random() * 15) - 7
    this.threatScore = Math.max(0, Math.min(100, this.threatScore + change))
    
    const element = document.getElementById('threat-score')
    if (element) {
      const current = parseInt(element.textContent) || 0
      this.animateNumber(element, current, this.threatScore, '/100')
      
      // Update alert level based on threat
      this.updateAlertLevel()
    }
  }

  updateMotionLevel() {
    const levels = ['Low', 'Medium', 'High', 'Very High']
    const weights = [40, 35, 20, 5]
    this.motionLevel = this.weightedRandom(levels, weights)
    
    const element = document.getElementById('motion-level')
    if (element) {
      element.textContent = this.motionLevel
      element.style.transition = 'color 0.3s ease'
      
      switch(this.motionLevel) {
        case 'Very High':
          element.style.color = '#e85d5d'
          break
        case 'High':
          element.style.color = '#e8a54b'
          break
        case 'Medium':
          element.style.color = '#7eb8ff'
          break
        default:
          element.style.color = '#3ecf8e'
      }
    }
  }

  checkFallDetection() {
    const fallProbability = 0.15
    this.fallDetected = Math.random() < fallProbability
    
    const element = document.getElementById('fall-status')
    if (element) {
      if (this.fallDetected) {
        element.textContent = 'DETECTED!'
        element.style.color = '#e85d5d'
        element.style.fontWeight = '600'
        this.addEvent('⚠️ Fall detected in sector B', 'warning')
        
        // Clear after 3 seconds
        setTimeout(() => {
          element.textContent = 'Clear'
          element.style.color = ''
          element.style.fontWeight = ''
          this.fallDetected = false
        }, 3000)
      }
    }
  }

  updateAlertLevel() {
    const badge = document.getElementById('alert-level')
    if (!badge) return
    
    badge.classList.remove('sg-badge--warn', 'sg-badge--danger')
    
    if (this.threatScore >= 70) {
      badge.textContent = 'Critical'
      badge.classList.add('sg-badge--danger')
    } else if (this.threatScore >= 40) {
      badge.textContent = 'Elevated'
      badge.classList.add('sg-badge--warn')
    } else {
      badge.textContent = 'Normal'
    }
  }

  generateRandomEvent() {
    const events = [
      { text: 'Camera 3 reconnected', type: 'info' },
      { text: 'Crowd density increased in sector A', type: 'info' },
      { text: 'Motion spike detected', type: 'warning' },
      { text: 'AI model inference completed', type: 'success' },
      { text: 'Unusual pattern detected', type: 'warning' },
      { text: 'System health check passed', type: 'success' },
      { text: 'Network latency spike', type: 'warning' }
    ]
    
    const event = events[Math.floor(Math.random() * events.length)]
    this.addEvent(event.text, event.type)
  }

  addEvent(message, type = 'info') {
    const log = document.getElementById('event-log')
    if (!log) return
    
    const ul = log.querySelector('ul')
    if (!ul) return
    
    const time = new Date().toLocaleTimeString('en-US', { hour12: false })
    const li = document.createElement('li')
    
    let icon = 'ℹ️'
    let color = '#8b909a'
    
    switch(type) {
      case 'warning':
        icon = '⚠️'
        color = '#e8a54b'
        break
      case 'danger':
        icon = '🚨'
        color = '#e85d5d'
        break
      case 'success':
        icon = '✅'
        color = '#3ecf8e'
        break
    }
    
    li.innerHTML = `<span style="color: ${color}">[${time}]</span> ${icon} ${message}`
    li.style.opacity = '0'
    li.style.transform = 'translateX(-10px)'
    li.style.transition = 'opacity 0.3s ease, transform 0.3s ease'
    
    ul.insertBefore(li, ul.firstChild)
    
    // Trigger animation
    setTimeout(() => {
      li.style.opacity = '1'
      li.style.transform = 'translateX(0)'
    }, 10)
    
    // Keep only last 20 events
    while (ul.children.length > 20) {
      ul.removeChild(ul.lastChild)
    }
    
    this.eventHistory.push({ time, message, type })
  }

  animateNumber(element, from, to, suffix = '') {
    const duration = 500
    const steps = 20
    const increment = (to - from) / steps
    let current = from
    let step = 0
    
    const timer = setInterval(() => {
      step++
      current += increment
      
      if (step >= steps) {
        element.innerHTML = `${to}<span class="sg-metric-suffix">${suffix}</span>`
        clearInterval(timer)
      } else {
        element.innerHTML = `${Math.round(current)}<span class="sg-metric-suffix">${suffix}</span>`
      }
    }, duration / steps)
  }

  weightedRandom(items, weights) {
    const totalWeight = weights.reduce((sum, w) => sum + w, 0)
    let random = Math.random() * totalWeight
    
    for (let i = 0; i < items.length; i++) {
      if (random < weights[i]) {
        return items[i]
      }
      random -= weights[i]
    }
    
    return items[items.length - 1]
  }

  getData() {
    return {
      personCount: this.personCount,
      threatScore: this.threatScore,
      motionLevel: this.motionLevel,
      fallDetected: this.fallDetected,
      eventHistory: this.eventHistory
    }
  }
}
