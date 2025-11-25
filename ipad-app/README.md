OpenMATB iPad App — Plan and Implementation Guide

Overview
This document describes how to build an iPad application that reproduces the OpenMATB experience with a modern iOS codebase. It covers setup, architecture, implementation milestones, replacing the joystick with touchscreen controls, quality practices, testing, and CI/CD. The implementation uses Swift, SwiftUI, and MVVM, following iOS best practices.

Goals
- Reach feature parity with the desktop app’s core tasks: tracking, system monitoring, communications, resource management, and scheduling.
- Replace the joystick with a responsive on-screen touchscreen control optimized for iPad (with optional pointer/trackpad support).
- Maintain the scenario-driven orchestration and CSV logging.
- Achieve high performance at 60+ FPS with predictable timing.
- Provide strong test coverage (unit, UI, snapshot, performance) and automated CI.

Prerequisites
- macOS with Xcode 15.4+ (or latest stable)
- iOS/iPadOS 17+ SDK
- A physical iPad (recommended) and iPad simulator
- Swift 5.9+

Recommended Tech Choices (Best Practices)
- UI: SwiftUI (native adaptive layout, accessibility, dynamic type, multi-scene)
- Architecture: MVVM with protocol-driven DI; optionally adopt The Composable Architecture (TCA) if preferred
- Concurrency: Swift Concurrency (async/await) and Combine for event streams where appropriate
- Modules: Feature-first organization with domain-oriented boundaries; use Swift Package Manager (SPM) for internal frameworks
- Styling: SwiftLint + SwiftFormat; follow API design guidelines; avoid force unwraps and implicit optionals
- Testing: XCTest (unit, UI), SnapshotTesting, Performance tests via XCTest + Instruments
- Logging/Telemetry: OSLog + Signposts, CSV session logs compatible with OpenMATB

Folder Structure (proposed)
- OpenMATB-iPad/
  - App/
    - OpenMATBApp.swift (App entry)
    - AppRouter.swift
  - Features/
    - Tracking/
      - TrackingView.swift
      - TrackingViewModel.swift
      - TouchInputService.swift
      - ReticleRenderer.swift
    - SystemMonitoring/
      - SystemMonitoringView.swift
      - SystemMonitoringViewModel.swift
    - Communications/
      - CommunicationsView.swift
      - CommunicationsViewModel.swift
    - ResourceManagement/
      - ResourceManagementView.swift
      - ResourceManagementViewModel.swift
    - Scheduling/
      - SchedulingView.swift
      - SchedulingViewModel.swift
  - Core/
    - Scenario/
      - ScenarioParser.swift
      - ScenarioEngine.swift
    - Time/
      - GameClock.swift (CADisplayLink-based)
    - Logging/
      - SessionLogger.swift (CSV)
    - Audio/
      - AudioService.swift
    - Localization/
      - LocalizedStrings.strings (en, fr)
    - DI/
      - AppContainer.swift
  - Shared/
    - UI/
      - Components (buttons, gauges, sliders)
      - Theme/
    - Utilities/
  - Resources/
    - Assets.xcassets (icons, task images)
    - Sounds/ (ported or equivalent)
    - Scenarios/ (text files compatible with existing format)
  - Tests/
    - Unit/
    - UI/
    - Snapshot/
    - Performance/

Step-by-Step: From Basics to Testing
1) Create the project
   - Open Xcode → Create a new App → “OpenMATB-iPad”
   - Interface: SwiftUI; Language: Swift; Platforms: iOS (iPad only or iPhone+iPad)
   - Set minimum iOS (iPadOS) target to 17.0+
   - Enable “Use Core Data” only if you plan persistent state (not required)

2) Add dependencies (SPM)
   - SwiftLint: https://github.com/realm/SwiftLint
   - SwiftFormat: https://github.com/nicklockwood/SwiftFormat
   - SnapshotTesting (pointfreeco): https://github.com/pointfreeco/swift-snapshot-testing
   - (Optional) The Composable Architecture: https://github.com/pointfreeco/swift-composable-architecture

3) Set up linting and formatting
   - Add .swiftlint.yml and .swiftformat configuration in repo root
   - Integrate a Run Script Phase in the Xcode build to enforce (or just gate in CI)

4) Define app scaffolding
   - Implement `OpenMATBApp` to inject the `AppContainer` (DI) into the environment
   - Create a root `DashboardView` that composes the five tasks in the standard layout
   - Use size classes and `GeometryReader` for adaptive panels

5) Implement the game clock and timing
   - Create `GameClock` backed by `CADisplayLink` (60 Hz, optionally 120 Hz on ProMotion)
   - Expose a `Publisher` (Combine) or `AsyncSequence` for ticks with precise timestamps
   - The `ScenarioEngine` subscribes to ticks to trigger events at the correct times

6) Scenario engine and parser
   - Maintain compatibility with `includes/scenarios/*.txt` syntax when possible
   - Implement `ScenarioParser` to parse lines into typed events (module, command, at time)
   - Implement `ScenarioEngine` to schedule events on the game clock and dispatch to feature view models
   - Add clear error reporting and strict validation (mimic Python validators)

7) Session logging (CSV)
   - Implement `SessionLogger` that writes CSV with schema: logtime,totaltime,scenario_time,type,module,address,value
   - Use `OSLog` signposts for performance marks; buffer CSV writes for I/O efficiency

8) Audio service
   - Use `AVAudioEngine` or `AVAudioPlayer` to play cues; preload buffers for low latency
   - Mirror the desktop sound set or provide equivalent assets

9) Replace joystick with touchscreen (tracking task)
   - Implement a virtual joystick area using SwiftUI gestures and haptics
   - Support: touch, Apple Pencil, and pointer (trackpad/mouse) via `UIPointerInteraction` or SwiftUI hover handlers
   - Provide both absolute mode (reticle follows finger) and relative mode (drag vector controls velocity)

   Example: Virtual joystick control (relative vector)
   ```swift
   import SwiftUI
   import Combine

   struct VirtualJoystickView: View {
       @Binding var axis: CGPoint // normalized [-1, 1] for x and y
       @State private var dragLocation: CGPoint? = nil
       private let radius: CGFloat = 80

       var body: some View {
           ZStack {
               Circle()
                   .fill(Color.secondary.opacity(0.2))
                   .frame(width: radius * 2, height: radius * 2)
               if let dragLocation {
                   Circle()
                       .fill(Color.accentColor)
                       .frame(width: 28, height: 28)
                       .position(x: clamp(dragLocation.x, -radius, radius) + radius,
                                 y: clamp(dragLocation.y, -radius, radius) + radius)
                       .animation(.interactiveSpring(), value: dragLocation)
               }
           }
           .contentShape(Circle())
           .gesture(
               DragGesture(minimumDistance: 0)
                   .onChanged { value in
                       let local = value.location - CGPoint(x: radius, y: radius)
                       let clamped = local.clamped(to: radius)
                       dragLocation = clamped
                       axis = CGPoint(x: clamped.x / radius, y: clamped.y / radius)
                   }
                   .onEnded { _ in
                       dragLocation = nil
                       axis = .zero
                   }
           )
           .frame(width: radius * 2, height: radius * 2)
           .accessibilityLabel("Virtual joystick")
           .accessibilityValue("x: \(axis.x, specifier: "%.2f"), y: \(axis.y, specifier: "%.2f")")
       }
   }

   private extension CGPoint {
       static let zero = CGPoint(x: 0, y: 0)
       static func - (lhs: CGPoint, rhs: CGPoint) -> CGPoint { .init(x: lhs.x - rhs.x, y: lhs.y - rhs.y) }
       func clamped(to r: CGFloat) -> CGPoint {
           let length = sqrt(x*x + y*y)
           guard length > r else { return self }
           let scale = r / max(length, 0.0001)
           return CGPoint(x: x * scale, y: y * scale)
       }
   }

   private func clamp(_ v: CGFloat, _ minV: CGFloat, _ maxV: CGFloat) -> CGFloat { max(minV, min(maxV, v)) }
   ```

   Mapping from Python joystick to touch vectors
   - Python: `device.x` and `device.y` in [-1, 1]
   - iPad: normalize drag vector to [-1, 1]; invert Y if needed to match desktop behavior
   - Sample integration in `TrackingViewModel`:
     - Subscribe to `axis` (Combine @Published) or bind via SwiftUI
     - Update reticle position every frame using `GameClock` delta: `reticle += axis * speed * dt`
   - Provide settings: axis inversion, sensitivity curves (linear, exponential), dead zone
   - Add subtle haptics on boundary hits or target acquisition (`UIImpactFeedbackGenerator`)
   - Add pointer support: treat pointer delta as axis, keep consistent mapping
   - Optional: if a hardware controller is connected (GCController), map directly to axis

10) Implement tracking module
   - `TrackingViewModel` owns reticle position, speed, target zone detection, scoring
   - `ReticleRenderer` draws with SwiftUI or a `MetalKit` view if you need >120 FPS headroom
   - Ensure center normalization and limits identical to desktop for score parity

11) Implement other feature modules
   - System Monitoring: Gauges and alerts; freeze arrows rules; overdue alarm visuals
   - Communications: UI for selecting/acknowledging channels; feedback borders
   - Resource Management: Pumps with on/off/failure states; tolerance indicators
   - Scheduling: Timeline(s), countdown/remaining time, visibility rules

12) Internationalization (i18n)
   - Use `Localizable.strings` for en/fr; configure `String(localized:)`
   - Map existing locales to iOS strings keys

13) Settings and configuration
   - App settings (scenario path, language, fullscreen behavior, clock speed) via `@AppStorage` or a settings screen
   - Scenario picker to run different protocol files from `Resources/Scenarios`

14) Testing (build confidence early)
   - Unit Tests: Scenario parsing, timing, scoring, logging
   - UI Tests: Launch app, start/stop scenarios, interact with controls
   - Snapshot Tests: Stable views for key states; record and assert diffs
   - Performance Tests: Measure frame time, parser time on large scenarios
   - Accessibility Tests: VoiceOver focus order, labels, contrast

15) Observability and diagnostics
   - Use `os_signpost` around frame loop, parser, and logger
   - In-app debug overlay: FPS, event queue length, reticle position, input axis

16) CI/CD
   - GitHub Actions (macos-latest):
     - xcodebuild build + test for iOS Simulator (iPad Pro target)
     - Run SwiftLint/SwiftFormat
     - Cache SPM
     - Archive on main branch
   - Fastlane:
     - lanes for test, beta (TestFlight), and release
     - automatic version bumping and changelog from Conventional Commits

17) App distribution
   - Configure App IDs, capabilities (audio), and signing
   - TestFlight builds for researchers/stakeholders

Milestones (example)
- Week 1: Project setup, clock, scenario parser skeleton, CSV logger
- Week 2: Tracking module with virtual joystick; parity on reticle dynamics
- Week 3: System Monitoring + Communications UIs and logic
- Week 4: Resource Management + Scheduling; consolidate scenario commands
- Week 5: i18n, accessibility, settings; stabilization
- Week 6: Testing hardening, performance tuning, CI/CD, TestFlight

Detailed Mapping: Desktop → iPad
- Joystick input → Virtual touchscreen joystick (DragGesture) and pointer; optional GCController
- Pyglet window loop → SwiftUI + CADisplayLink-backed `GameClock`
- Python scenario text files → `ScenarioParser` producing domain events
- Logging to CSV → `SessionLogger` writing to app sandbox with share/export
- Audio cues → `AVAudioEngine` preloaded buffers
- Widgets/components → SwiftUI views with comparable states and accessibility

Quality and Coding Standards
- SOLID, protocol-oriented design, clear boundaries between Feature/ViewModel/Service
- Strict nullability: avoid `!`, prefer safe unwrapping and early exits
- Pure view models (no UIKit/SwiftUI imports), deterministic logic, decoupled from the view
- Minimize singletons; inject dependencies as protocols via `AppContainer`
- Deterministic time via `GameClock` abstraction (mockable in tests)
- Document public APIs with Swift documentation comments; keep functions small and intention-revealing

Touchscreen Best Practices (replacing joystick)
- Latency: minimize gesture processing work; avoid heavy layouts in `onChanged`; offload to view model
- Sampling: update at display refresh (link input to `GameClock`) for smooth motion
- Normalization: map gesture deltas to [-1, 1] with configurable sensitivity and dead zones
- Consistency: provide axis inversion toggles to match desktop behavior
- Feedback: use subtle haptics for key events; visual clamp indicators
- Accessibility: ensure the joystick area is large, has clear affordances, supports VoiceOver descriptors

Testing Strategy (concrete)
- Unit
  - `ScenarioParserTests`: valid/invalid lines, timing edge cases
  - `TrackingViewModelTests`: axis mapping, dead zone, scoring in/out target
  - `GameClockTests`: tick accuracy and pause/resume
- UI
  - Launch and load scenario list; start/stop scenario; interact with tracking control
  - Validate alarms visible within deadlines
- Snapshot
  - Key feature screens in several locales and size classes
- Performance
  - Parser throughput on large scenario files
  - Frame time under typical interaction (target < 16.7 ms/frame @60Hz)

CI Example (high level)
- macos-14 runner
- Steps: checkout → Xcode version select → SPM resolve cache → swiftformat --lint → swiftlint → xcodebuild test -scheme OpenMATB-iPad -destination "platform=iOS Simulator,name=iPad Pro (11-inch)" → artifact test reports → optional fastlane beta

Running and Debugging
- Use the iPad Pro (11-inch) simulator for layout
- Toggle a debug overlay with FPS and input axis
- Use Instruments (Time Profiler, Core Animation, Allocations) to tune frame pacing

Notes on Asset and Scenario Parity
- Port assets and sounds to `Assets.xcassets` and `Resources/Sounds`
- Convert scenario files as-is when possible; otherwise document deviations
- Keep scoring and timing rules identical to desktop for research consistency

License and Attributions
- Respect OpenMATB license and include attributions where required
- Cite original references as appropriate

Next Steps
- Initialize the Xcode project and scaffold the `Core` and `Features` layers
- Implement `GameClock`, `ScenarioParser`, and the Tracking module with the virtual joystick
- Establish tests and CI early to lock behavior

