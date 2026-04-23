/**
 * Mini Charts Module
 * Lightweight canvas-based charts without external dependencies
 */

export class MiniChart {
  constructor(canvasId, options = {}) {
    this.canvas = document.getElementById(canvasId)
    if (!this.canvas) return
    
    this.ctx = this.canvas.getContext('2d')
    this.data = []
    this.maxDataPoints = options.maxDataPoints || 30
    this.color = options.color || '#3ecf8e'
    this.fillColor = options.fillColor || 'rgba(62, 207, 142, 0.1)'
    this.lineWidth = options.lineWidth || 2
    this.maxValue = options.maxValue || 100
    
    this.setupCanvas()
  }

  setupCanvas() {
    const dpr = window.devicePixelRatio || 1
    const rect = this.canvas.getBoundingClientRect()
    
    this.canvas.width = rect.width * dpr
    this.canvas.height = rect.height * dpr
    
    this.ctx.scale(dpr, dpr)
    this.canvas.style.width = rect.width + 'px'
    this.canvas.style.height = rect.height + 'px'
  }

  addDataPoint(value) {
    this.data.push(value)
    if (this.data.length > this.maxDataPoints) {
      this.data.shift()
    }
    this.draw()
  }

  draw() {
    const rect = this.canvas.getBoundingClientRect()
    const width = rect.width
    const height = rect.height
    
    this.ctx.clearRect(0, 0, width, height)
    
    if (this.data.length < 2) return
    
    const stepX = width / (this.maxDataPoints - 1)
    const scaleY = height / this.maxValue
    
    // Draw filled area
    this.ctx.beginPath()
    this.ctx.moveTo(0, height)
    
    this.data.forEach((value, index) => {
      const x = index * stepX
      const y = height - (value * scaleY)
      
      if (index === 0) {
        this.ctx.lineTo(x, y)
      } else {
        this.ctx.lineTo(x, y)
      }
    })
    
    this.ctx.lineTo((this.data.length - 1) * stepX, height)
    this.ctx.closePath()
    this.ctx.fillStyle = this.fillColor
    this.ctx.fill()
    
    // Draw line
    this.ctx.beginPath()
    this.data.forEach((value, index) => {
      const x = index * stepX
      const y = height - (value * scaleY)
      
      if (index === 0) {
        this.ctx.moveTo(x, y)
      } else {
        this.ctx.lineTo(x, y)
      }
    })
    
    this.ctx.strokeStyle = this.color
    this.ctx.lineWidth = this.lineWidth
    this.ctx.stroke()
  }

  clear() {
    this.data = []
    const rect = this.canvas.getBoundingClientRect()
    this.ctx.clearRect(0, 0, rect.width, rect.height)
  }
}

export class ThreatGauge {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId)
    if (!this.canvas) return
    
    this.ctx = this.canvas.getContext('2d')
    this.value = 0
    this.targetValue = 0
    
    this.setupCanvas()
  }

  setupCanvas() {
    const dpr = window.devicePixelRatio || 1
    const size = 120
    
    this.canvas.width = size * dpr
    this.canvas.height = size * dpr
    
    this.ctx.scale(dpr, dpr)
    this.canvas.style.width = size + 'px'
    this.canvas.style.height = size + 'px'
  }

  setValue(value) {
    this.targetValue = Math.max(0, Math.min(100, value))
    this.animate()
  }

  animate() {
    const diff = this.targetValue - this.value
    if (Math.abs(diff) < 0.5) {
      this.value = this.targetValue
      this.draw()
      return
    }
    
    this.value += diff * 0.1
    this.draw()
    requestAnimationFrame(() => this.animate())
  }

  draw() {
    const size = 120
    const centerX = size / 2
    const centerY = size / 2
    const radius = 45
    
    this.ctx.clearRect(0, 0, size, size)
    
    // Background arc
    this.ctx.beginPath()
    this.ctx.arc(centerX, centerY, radius, 0.75 * Math.PI, 2.25 * Math.PI)
    this.ctx.strokeStyle = '#252830'
    this.ctx.lineWidth = 8
    this.ctx.stroke()
    
    // Value arc
    const endAngle = 0.75 * Math.PI + (this.value / 100) * 1.5 * Math.PI
    
    this.ctx.beginPath()
    this.ctx.arc(centerX, centerY, radius, 0.75 * Math.PI, endAngle)
    
    // Color based on value
    let color = '#3ecf8e'
    if (this.value >= 70) color = '#e85d5d'
    else if (this.value >= 40) color = '#e8a54b'
    
    this.ctx.strokeStyle = color
    this.ctx.lineWidth = 8
    this.ctx.lineCap = 'round'
    this.ctx.stroke()
    
    // Center text
    this.ctx.fillStyle = '#eceef2'
    this.ctx.font = 'bold 24px Roboto'
    this.ctx.textAlign = 'center'
    this.ctx.textBaseline = 'middle'
    this.ctx.fillText(Math.round(this.value), centerX, centerY)
  }
}
