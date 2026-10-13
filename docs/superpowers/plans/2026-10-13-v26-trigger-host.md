# V26 Trigger Host Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline; user approved continuous implementation, testing and packaging without further stage gates on 2026-10-13.

**Goal:** Deliver a Python/Windows V26 acquisition host supporting all six requested controls and offline trigger-relative plots.
**Architecture:** Keep the existing plotting stack and legacy core as a reference; route the new GUI to a V26 session with one socket-owning scheduler and a bounded disk writer. Typed configuration/status parsing has no GUI dependency.
**Tech Stack:** Python 3.12, Tkinter, NumPy 2.2.6, Matplotlib 3.10.3, unittest, GitHub Actions/PyInstaller.
**Spec:** ../specs/2026-10-13-v26-trigger-host-design.md

## Global constraints
- 100000000 Hz, unsigned big-endian voltage/current U12 stored in U16; 8 ASCII characters per pair.
- TIME 1–200 ms or SAMPLES 1–20000000; PRE 0–100; MODE 0/1; comparisons 0–4; enable 0–3; gap 0–600000 ms.
- One command in flight; no queries during GET; ARM acceptance is not DONE; force only manual/history-ready.
- No firmware changes or invented ADC-to-A calibration. Preserve prior voltage conversion.
- New branch codex/v26-trigger-host; preserve main and V3. Reuse already installed dependencies for local tests.

## Review focus
- Replies arriving late after timeouts must never be assigned to the next command (session timeout test).
- Cancellation may race with DONE (ABORT-rejected/RELEASE test).
- A full writer queue and failed disk cannot leave the socket worker blocked forever (writer failure test).
- Recovered records have unknown active mode/thresholds (reconnect test).
- PRE=100 puts trigger beyond last sample, and missing metadata must not invent a trigger (recording/plot smoke).

## Tasks
### 1. Protocol values and state gates
Files: ad_host/v26_protocol.py; tests/test_v26_protocol.py.
Interfaces: AcquisitionSettings.command(verb), .samples, .pre_samples; parse_tst(text)->dict; parse_fst(text)->dict; can_arm/status, can_get/status, can_force(status,active), can_release/status; validate_record(status,active=None).
- [x] Write and run failing tests for legal commands, field bases, FST SET commas, masks, metadata consistency and bounds.
- [x] Implement pure validation/encoding; rerun tests.

### 2. Serial session and file lifecycle
Files: ad_host/v26_session.py, ad_host/v26_transport.py; tests/test_v26_session.py; tools/v26_simulator.py.
Interfaces: V26Session(CaptureConfig,command_timeout=5,progress_timeout=30,poll_interval=.1).start/stop/wait, submit(action,settings=None,repeat=False), snapshot/events. Actions configure/start/force/cancel/read/release/stop_repeat/query; snapshot exposes state, status, active_settings, can_*, receiving, last_path, counts, error, repeat, diagnostics.
- [x] Write real loopback tests for manual, automatic repeat/gap, framing, failure/cancel/timeout, metadata and disk completion.
- [x] Implement one IO thread, bounded writer, immutable active config, validated DONE->GET flow and recovery; keep legacy core tests as regression.
- [x] Run suite and representative 160MB transfer simulation.

### 3. Trigger-aware recording and GUI
Files: ad_host/recording.py, plot_window.py, gui.py, __init__.py; tests/test_v26_recording.py; tools/gui_smoke.py, tools/plot_smoke.py.
- [x] Write failing tests for JSON trigger origin/validation/current12bits, preserving old files without trigger metadata.
- [x] Add metadata to Recording and use it in make_view/zoom/trigger markers.
- [x] Replace acquisition screen with V26 tabbed controls, state-driven buttons and diagnostic commands; preserve offline popup.
- [x] Windows real-Tk smoke tests perform manual trigger and validate controls, relative axis, export/reopen.

### 4. Documentation, review and delivery
Files: README.md, docs/QUICKSTART.md, docs/OFFLINE_PLOTTING.md, .github/workflows/ci.yml.
- [x] Document trigger limitations, workflows, partial files, recovery, protocol evidence and usage.
- [x] Run all tests, request independent whole-change review and fix important findings with regressions.
- [ ] Push changes to requested branch, run Windows/Linux CI and Windows packaging; verify source and binary ZIP outputs.
- [ ] Report branch, usable downloads, six-feature support and actual hardware-validation limitation.

## Execution ledger
- Baseline copied from V3 into isolated ordinary directory (workspace has no local git repository); GitHub connector supplies branch history.
- Initial local suite encountered a permission error opening installed NumPy in one test import; investigate environment before treating as product regression.
- Ruling: user explicitly waived further stage confirmations; execute plan inline, use one final code reviewer, and publish to already authorized branch.

### Verified implementation, 2026-10-13
- Local full suite: 47 tests pass. The initial dependency permission issue was resolved; no product change required.
- 20,000,000-pair / 160 MB loopback GET at simulated 6 MB/s completed in 32.89 s; SHA-256 exactly matched expected bytes, peak queued data about 0.06 MiB. This is not a board throughput measurement.
- First Windows/Linux CI passed, including real Tk acquisition, trigger-relative zoom, PNG export/reopen, legacy GUI regression and PyInstaller build (run 38396978577). Final revision CI/package verification follows the final push.
- Independent whole-change review completed. Regression fixes cover metadata publication failure, configuration edits during repeat gap, stop-repeat during ARM acknowledgment, rejected-but-executed ARM retaining stale settings, and duplicate Connect activation.
- Implementation layout: new v26_gui.py is the run.py / module entry point; legacy gui.py/core.py remain for compatibility regression. Raw ACQ input follows verified CFG + TST + ARM; unsafe arbitrary command bypass is intentionally unavailable as designed.
- Local bundled Tcl initialization is unavailable; real GUI checks run on Windows CI. Physical STM32/FPGA validation remains outstanding and is not claimed by software tests.
