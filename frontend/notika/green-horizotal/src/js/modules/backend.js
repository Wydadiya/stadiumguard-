/**
 * Backend Connection Module
 * Gère la connexion avec l'API Python StadiumGuard
 * Polle les endpoints individuels (person, fall, motion, audio, smoke) ET alert si disponible.
 */

export class BackendConnector {
  constructor(baseUrl = 'http://localhost:5000') {
    this.baseUrl = baseUrl
    this.isConnected = false
    this.lastError = null
    this.pollInterval = null
    this.isFetching = false
    this.callbacks = {
      onData: null,
      onError: null,
      onConnect: null,
      onDisconnect: null
    }
  }

  /**
   * Démarre le polling de l'API backend
   * @param {number} intervalMs - Intervalle de polling en ms (défaut: 500ms)
   */
  startPolling(intervalMs = 500) {
    if (this.pollInterval) {
      this.stopPolling()
    }

    // Premier appel immédiat
    this.fetchAllData()

    // Puis polling régulier
    this.pollInterval = setInterval(() => {
      this.fetchAllData()
    }, intervalMs)

    console.log(`✅ Backend polling started (${intervalMs}ms interval)`)
  }

  /**
   * Arrête le polling
   */
  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval)
      this.pollInterval = null
      console.log('⏸️ Backend polling stopped')
    }
  }

  /**
   * Récupère toutes les données des 3 labs + alert en parallèle.
   * Construit un objet unifié même si l'orchestrateur n'est pas lancé.
   */
  async fetchAllData() {
    if (this.isFetching) {
      return null
    }

    this.isFetching = true

    try {
      // Poller les endpoints individuels en parallèle
      const [personData, fallData, motionData, audioData, smokeData, alertData] = await Promise.all([
        this.fetchEndpointSafe('person'),
        this.fetchEndpointSafe('fall'),
        this.fetchEndpointSafe('motion'),
        this.fetchEndpointSafe('audio'),
        this.fetchEndpointSafe('smoke'),
        this.fetchEndpointSafe('alert')
      ])

      // Marquer comme connecté si au moins un endpoint répond
      const anyData = personData || fallData || motionData || audioData || smokeData || alertData
      if (anyData && !this.isConnected) {
        this.isConnected = true
        this.lastError = null
        if (this.callbacks.onConnect) {
          this.callbacks.onConnect()
        }
      }

      // Si l'orchestrateur tourne, utiliser ses données fusionnées
      if (alertData && !alertData.error) {
        if (this.callbacks.onData) {
          // Enrichir avec les données individuelles si disponibles
          alertData._individual = {
            person: personData,
            fall: fallData,
            motion: motionData,
            audio: audioData,
            smoke: smokeData
          }
          this.callbacks.onData(alertData)
        }
        return alertData
      }

      // Sinon, construire un objet unifié à partir des 3 labs
      const personScore = personData?.score ?? 0
      const fallScore = fallData?.score ?? 0
      const motionScore = motionData?.score ?? 0
      const audioScore = audioData?.score ?? 0
      const smokeScore = smokeData?.score ?? 0

      // Formule de fusion simplifiée (même pondérations que orchestrator.py)
      const W_PERSON = 0.15
      const W_FALL = 0.30
      const W_MOTION = 0.30
      const W_AUDIO = 0.25
      const rawVision = personScore * W_PERSON + fallScore * W_FALL + motionScore * W_MOTION
      const rawAudio = audioScore * W_AUDIO
      const rawCombined = rawVision + rawAudio
      const finalScore = Math.min(rawCombined, 100)

      // Niveau d'alerte
      let level = 'LOW'
      if (finalScore >= 80) level = 'CRITICAL'
      else if (finalScore >= 60) level = 'HIGH'
      else if (finalScore >= 30) level = 'MEDIUM'

      const unifiedData = {
        timestamp: Math.max(
          personData?.timestamp ?? 0,
          fallData?.timestamp ?? 0,
          motionData?.timestamp ?? 0,
          audioData?.timestamp ?? 0
        ),
        final_score: Math.round(finalScore * 10) / 10,
        level: level,
        raw_vision: Math.round(rawVision * 10) / 10,
        raw_audio: Math.round(rawAudio * 10) / 10,
        raw_combined: Math.round(rawCombined * 10) / 10,
        scores: {
          person: Math.round(personScore * 10) / 10,
          fall: Math.round(fallScore * 10) / 10,
          motion: Math.round(motionScore * 10) / 10,
          audio: Math.round(audioScore * 10) / 10,
          smoke: Math.round(smokeScore * 10) / 10
        },
        raw: {
          person: personData?.details ?? {},
          fall: fallData?.details ?? {},
          motion: motionData?.details ?? {},
          audio: audioData?.details ?? {},
          smoke: smokeData?.details ?? {}
        },
        _source: 'frontend_fusion',
        _individual: {
          person: personData,
          fall: fallData,
          motion: motionData,
          audio: audioData,
          smoke: smokeData
        }
      }

      if (this.callbacks.onData) {
        this.callbacks.onData(unifiedData)
      }

      return unifiedData

    } catch (error) {
      console.error('❌ Backend fetch error:', error.message)
      this.lastError = error.message

      if (this.isConnected) {
        this.isConnected = false
        if (this.callbacks.onDisconnect) {
          this.callbacks.onDisconnect(error)
        }
      }

      if (this.callbacks.onError) {
        this.callbacks.onError(error)
      }

      return null
    } finally {
      this.isFetching = false
    }
  }

  /**
   * Récupère les données d'un endpoint spécifique (sans throw)
   * @param {string} endpoint - person, fall, motion, alert, context
   */
  async fetchEndpointSafe(endpoint) {
    try {
      const response = await fetch(`${this.baseUrl}/api/${endpoint}`, {
        method: 'GET',
        mode: 'cors',
        headers: {
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        return null
      }

      return await response.json()

    } catch (error) {
      return null
    }
  }

  /**
   * Récupère les données d'un endpoint spécifique (avec throw)
   * @param {string} endpoint - person, fall, motion, context
   */
  async fetchEndpoint(endpoint) {
    try {
      const response = await fetch(`${this.baseUrl}/api/${endpoint}`, {
        method: 'GET',
        mode: 'cors',
        headers: {
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      return await response.json()

    } catch (error) {
      console.error(`❌ Error fetching ${endpoint}:`, error.message)
      return null
    }
  }

  /**
   * Vérifie la santé du serveur backend
   */
  async checkHealth() {
    try {
      const response = await fetch(`${this.baseUrl}/api/health`, {
        method: 'GET',
        mode: 'cors'
      })

      if (!response.ok) {
        return { status: 'error', message: `HTTP ${response.status}` }
      }

      const data = await response.json()
      return { status: 'ok', data }

    } catch (error) {
      return { status: 'error', message: error.message }
    }
  }

  /**
   * Enregistre un callback pour les données reçues
   */
  onData(callback) {
    this.callbacks.onData = callback
  }

  /**
   * Enregistre un callback pour les erreurs
   */
  onError(callback) {
    this.callbacks.onError = callback
  }

  /**
   * Enregistre un callback pour la connexion
   */
  onConnect(callback) {
    this.callbacks.onConnect = callback
  }

  /**
   * Enregistre un callback pour la déconnexion
   */
  onDisconnect(callback) {
    this.callbacks.onDisconnect = callback
  }

  /**
   * Retourne l'état de connexion
   */
  getConnectionStatus() {
    return {
      connected: this.isConnected,
      lastError: this.lastError,
      baseUrl: this.baseUrl
    }
  }
}
