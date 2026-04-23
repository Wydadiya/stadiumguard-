Place your robot voice prompts in this folder with these exact names:

- bienvenu.aac
- attention_liberer_passage.aac
- alerte.aac
- Incident.aac

Accepted input formats:
- aac / mp3 / wav

Server conversion:
- The backend converts input files on the fly to:
  WAV PCM, mono, 8-bit unsigned, 16000 Hz
  so the ESP32 can play them reliably.

These files are served by:
- GET /api/robot/audio-stream?event=welcome   -> bienvenu.aac
- GET /api/robot/audio-stream?event=obstacle  -> attention_liberer_passage.aac
- GET /api/robot/audio-stream?event=gas_emergency -> alerte.aac
- GET /api/robot/audio-stream?event=ai_alert  -> Incident.aac
