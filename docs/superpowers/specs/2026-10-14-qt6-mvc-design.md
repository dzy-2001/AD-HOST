Design and execution brief, 2026-10-14

Goal: AD-HOST 0.5.0 PyQt6 desktop UI, QtAwesome icon/text actions, user's Nord Light GLOBAL_STYLE, MVC directories. Existing firmware identity checks remain disabled. Existing acquisition and file semantics stay intact.

Chosen approach: PyQt6 matches the user's companion project. Keep Matplotlib's Qt canvas and existing peak-preserving sampler. Replacing with pyqtgraph or QML would broaden dependencies and change export/plot behavior without a current need.

Model: src/models holds current core, commands, recording, v26_protocol/session/transport plus pure waveform sample lookup/range calculations. No Qt dependencies. ad_host imports become compatibility aliases for existing clients and regression tests.
View: src/views main_window.py, waveform_window.py and widgets/styles.py (unchanged supplied content), theme.py and reusable controls. Widgets emit intent signals; do not own sockets or parse files.
Controller: acquisition_controller.py owns session lifecycle and 100ms snapshot timer; waveform_controller.py owns asynchronous load/view requests, cancellation, latest-only range refresh, navigation and raw-sample cursor measurements.

Main UI: shared connection card + three tabs acquisition/records/diagnostics, numeric fields, state-driven buttons, throughput/buffer/record status. Record window: Qt Matplotlib canvas, QTA toolbar modes pan/box zoom/measurement, wheel zoom about pointer, shared X axes, reset overview, return to trigger, fit Y, range fields, PNG export, hover crosshair and draggable A/B markers with raw-based delta readouts.

Threading: reuse single socket owner and bounded writer; GUI never performs networking or parsing. Waveform work uses a Python worker with bounded latest-request mailbox and cancellation, GUI polls results with QTimer; only GUI thread touches Qt or Matplotlib. Closing cancels work and clears pending large data; application exit waits asynchronously for workers/session completion.

Styling: copy supplied styles.py exactly at text level. Extend separately for tabs/status/progress and restore visible arrows/checkmarks using QtAwesome-generated assets; fix selected-text contrast in extension, not supplied stylesheet. Icons always have text/tooltips.

Validation: existing protocol/capture tests; new raw cursor index/time/delta and range tests; Qt controller cancellation/reopen/stale-result tests; full offscreen Qt capture/plot/navigation/PNG smoke on Windows/Linux; Windows packaged executable smoke and screenshots for visual QA. Review final change once with a fresh reviewer per executing-plans skill. Package code/Windows app in new codex/qt6-mvc-host branch.

Execution sequence:
1. Isolate from 0.4.1; preserve styling source; pure model move and sample calculations with regression tests.
2. Qt views, common theme and controller contract; reproduce behavior using loopback simulator.
3. Waveform worker/controller and interaction tests, including cancel while parsing and close/reopen.
4. Entry/dependencies/CI/docs, whole-change review, fixes, build ZIP/hash/source agreement.

Review focus: never drop stop-repeat state; no networking on GUI thread; no stale data/results after close/reload; cursor reads original samples; bounded waveform jobs on repeated drag; no 0.4.1 strict version checks reintroduced; packaged icons/fonts available.

Authorization: user already requested continuous implementation/testing/packaging without further stage confirmations. Implement inline. No architectural choices requiring new user input remain.


Execution ledger
- Model move preserves baseline implementations; compatibility aliases passed all 49 existing tests. Four raw sample/range tests and two background cancellation tests added (55 tests before Qt interaction coverage).
- Shared styles.py matches supplied source exactly as normalized UTF-8 text (SHA256 f23520d43f19c78210f39cc022e509d3da0ec4d7a25ccb5c224cf11e34b4b53b). All visual corrections are in theme.py.
- Windows and Linux Qt workflow smoke passed; Windows native-platform screenshots reviewed for Chinese font rendering and control visibility. Linux CI supplies EGL/OpenGL/xkbcommon and CJK fonts.
- Independent review found stale pending range after Overview, reentrant close, and disabled y autoscaling after pan/zoom. Four real Qt regression tests reproduced all failures on run 38504905724; corrected by invalidation, queued close, and explicit y-autoscale enabling. Final green/build verification recorded in delivery report.
- Local security environment prevents loading the Qt extension in the same process as the existing plotting dependency tree. GUI validation therefore runs on CI; local non-GUI tests remain usable. This is a test-environment limitation, not a bundled-program limitation.
- User's continuous-execution authorization used throughout; no further approval gates or additional implementer agents. One read-only whole-change reviewer completed; no deferred review findings.
