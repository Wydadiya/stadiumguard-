# StadiumGuard — AI stadium monitoring dashboard (frontend)

**StadiumGuard** is a minimal, production-oriented dashboard shell for real-time AI stadium monitoring. It is built on a trimmed **Notika** / **Colorlib** Bootstrap layout, modernized with **Vite 7.3.1**, **Bootstrap 5.3.8**, and **ES6 modules** — no jQuery.

The app ships as a **single page** (`notika/green-horizotal/index.html`): live video placeholder, AI metric panels, threat score, and event log. **No backend or AI logic** is included; wire your streams and inference into the documented DOM hooks.

The original multi-page Notika demo (41 HTML pages, charts, maps, email, and so on) was removed to keep the bundle small and focused.

## Quick start

```bash
git clone https://github.com/nicdev/notika.git
cd notika
npm install
npm run dev        # http://localhost:3100 — opens the StadiumGuard dashboard
```

Production build:

```bash
npm run build      # output: dist/
npm run preview    # http://localhost:4173
```

## Features (current fork)

- **Vite 7.3** — HMR, SCSS (`modern-compiler`), PostCSS (autoprefixer + cssnano), single HTML entry
- **Bootstrap 5.3.8** — layout, badges, utilities
- **Font Awesome 7.2** — tree-shaken solid icons (only icons used on the dashboard are bundled)
- **`NotikaUI`** (`src/js/modules/ui.js`) — Bootstrap widgets, optional counters, toasts
- **Real-time Data Simulator** — Live demo mode with animated metrics and events
- **Mini Charts** — Lightweight canvas-based charts for person count and threat score
- **Interactive Controls** — Start/stop simulation, clear event log
- **Smooth Animations** — Fade-in effects, hover states, pulsing indicators
- **Tooltips** — Hover over metrics for detailed descriptions
- **Minimal dark UI** — `src/css/modern.scss` only (no legacy `style.css`); optional stadium background image under a dark scrim

## Dynamic Features

### Data Simulator
The dashboard includes a built-in data simulator that generates realistic monitoring data:
- Person count fluctuations (0-500)
- Threat score changes (0-100)
- Motion level detection (Low, Medium, High, Very High)
- Fall detection alerts
- Random system events

Click **"Start Demo"** to activate the simulation and see the dashboard come alive with real-time updates.

### Live Charts
Two mini-charts visualize data trends:
- **Person Count Chart** — Shows crowd size over time
- **Threat Score Chart** — Displays threat level history

Charts update every second during simulation and use smooth animations.

### Interactive Elements
- **Animated metrics** — Numbers count up smoothly when values change
- **Color-coded alerts** — Threat levels change color based on severity
- **Pulsing indicators** — System status dot pulses to show activity
- **Event log** — Auto-scrolling log with timestamped events
- **Hover effects** — Cards lift and glow on hover
- **Tooltips** — Descriptive tooltips on all metric cards

## Integration hooks (DOM IDs)

| ID | Intended use |
| --- | --- |
| `#video-stream` | Mount WebRTC, HLS, or `<video>` |
| `#person-count` | Person count |
| `#fall-status` | Fall detection status text |
| `#motion-level` | Motion level label or value |
| `#threat-score` | Threat score (e.g. 0–100) |
| `#event-log` | Append timestamped events |
| `#system-status` | System health text |
| `#alert-level` | Alert badge (optional classes `sg-badge--warn` / `sg-badge--danger` for emphasis) |

At runtime, `window.StadiumGuard` holds the app instance; `window.bootstrap` exposes Bootstrap's JS API.

## Technology stack

| Package | Role |
| --- | --- |
| Vite 7.3.1 | Build and dev server |
| Bootstrap 5.3.8 | CSS + JS |
| Font Awesome 7.2 | Icons (`@fortawesome/fontawesome-svg-core`, `@fortawesome/free-solid-svg-icons`) |
| Day.js 1.11 | Used by `NotikaUI` |
| Sass, PostCSS, cssnano, autoprefixer | Styles pipeline |

## Project structure

```text
vite.config.js              # Vite root: notika/green-horizotal; plugins: none
package.json
notika/green-horizotal/
  index.html
  images/                   # Stadium background (morocco-3-min.jpg)
  src/js/main.js            # Bootstrap + modern.scss + Font Awesome + NotikaUI
  src/js/modules/
    ui.js                   # Bootstrap components and notifications
    simulator.js            # Real-time data simulation
    charts.js               # Lightweight canvas charts
  src/css/modern.scss       # All UI styles
  img/logo/notika-icon.svg  # Favicon / logo (publicDir)
```

## API Usage

### Starting/Stopping Simulation
```javascript
// Access the app instance
const app = window.StadiumGuard

// Start simulation
app.simulator.start()

// Stop simulation
app.simulator.stop()

// Get current data
const data = app.simulator.getData()
console.log(data.personCount, data.threatScore)
```

### Adding Custom Events
```javascript
// Add event to log
app.simulator.addEvent('Custom event message', 'info') // types: info, warning, danger, success
```

### Showing Notifications
```javascript
// Show toast notifications
app.ui.showSuccess('Operation completed')
app.ui.showError('Something went wrong')
app.ui.showWarning('Warning message')
app.ui.showInfo('Information')
```

## Original template

Notika is licensed under the MIT License. Attribution to [Colorlib](https://colorlib.com) as the original Notika author applies to the template assets. The upstream multi-page demo lives on [Colorlib's Notika page](https://colorlib.com/polygon/notika/index.html).

## License

MIT — see the license terms in the repository and the Colorlib attribution above.
