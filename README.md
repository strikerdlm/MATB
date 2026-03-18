# 🛩️ UAV & Fighter Aircraft Monitoring System

A real-time, visually stunning terminal-based monitoring system for UAV (Unmanned Aerial Vehicle) and Fighter Aircraft operations with realistic mission challenges.

## ✨ Features

- **Rich Terminal UI**: Beautiful, modern terminal interface with live updates
- **UAV Monitoring**: Track drone operations including surveillance, reconnaissance, and delivery missions
- **Fighter Aircraft Ops**: Monitor combat aircraft with radar, weapons systems, and tactical operations
- **Real-time Events**: Dynamic event sequences with realistic challenges
- **Mission Objectives**: Track mission progress with visual indicators
- **Threat Detection**: Simulated radar and threat warning systems
- **System Health**: Monitor fuel, battery, weapons, and system status

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the monitoring system
python -m aircraft_monitor

# Or run specific modules
python -m aircraft_monitor.demo_uav      # UAV operations demo
python -m aircraft_monitor.demo_fighter  # Fighter aircraft demo
python -m aircraft_monitor.demo_combined # Combined operations

# Optional runtime flags
python -m aircraft_monitor fighter --event-delay 0.35
python -m aircraft_monitor combined --headless
```

## 🧪 Non-interactive / CI usage

When stdout/stderr are not attached to a TTY (for example, in CI logs), the app:

- Runs in **headless mode** (prints a readable event stream instead of a full-screen UI)
- Avoids blocking on interactive prompts (defaults to `combined` mode when no mode is provided)
- Supports explicit override via environment variable:
  - `AIRCRAFT_MONITOR_HEADLESS=true` forces headless mode
  - `AIRCRAFT_MONITOR_HEADLESS=false` forces full-screen mode

### CLI Options

- `mode` (optional positional): `uav`, `fighter`, or `combined`
- `--event-delay <seconds>`: set frame/event pacing (`0.05` to `5.0`)
- `--headless`: force non-interactive stream output

## 📦 Project Structure

```
aircraft_monitor/
├── __init__.py           # Package initialization
├── __main__.py           # Entry point
├── models/               # Data models
│   ├── __init__.py
│   ├── uav.py           # UAV model
│   └── fighter.py       # Fighter aircraft model
├── events/               # Event system
│   ├── __init__.py
│   ├── base.py          # Base event classes
│   ├── uav_events.py    # UAV-specific events
│   └── fighter_events.py # Fighter-specific events
├── visualization/        # Rich UI components
│   ├── __init__.py
│   ├── dashboard.py     # Main dashboard
│   ├── panels.py        # UI panels
│   └── themes.py        # Color themes
├── simulation/           # Simulation engine
│   ├── __init__.py
│   └── engine.py        # Event simulation
├── demo_uav.py          # UAV demo
├── demo_fighter.py      # Fighter demo
└── demo_combined.py     # Combined demo
```

## 🎮 Controls

During simulation:
- Press `Ctrl+C` to gracefully exit
- Events auto-progress with realistic timing

## 📊 Visualization Components

- **Status Panels**: Real-time aircraft status with gauges
- **Event Timeline**: Scrolling event log with severity colors
- **Radar Display**: ASCII radar with threat indicators
- **Mission Progress**: Visual progress bars for objectives
- **System Health**: Fuel, weapons, and sensor status

## 🔧 Configuration

Customize simulation parameters in the demo files or create your own scenarios.

## 🗺️ Roadmap

- **Determinism**: Optional seeded randomness for reproducible demos and screenshots
- **Scientific consistency**: Keep key units internally consistent (e.g., Mach ↔ knots conversions)
- **Reliability**: Bounded event streams, safer defaults in non-interactive environments
- **Quality**: Add automated smoke tests for the demo entrypoints

## 📄 License

MIT License - See LICENSE file for details.
