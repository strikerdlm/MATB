"""Synthetic native audio/keyboard check; no participant or study session is used.

Run with the station's OpenMATB interpreter from the repository root. The test
dispatches keyboard events through the native window and retains evidence.
Speaker audibility and physical key actuation still require a person.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=["es_CO", "en_EN"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--briefing", action="store_true", help="Verify the standalone Spanish briefing instead of the timed block")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    runtime = root / "openmatb"
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sessions = out / "sessions"
    sessions.mkdir()
    idiom = "spanish" if args.language == "es_CO" else "english"
    scenario = out / "scenario.txt"
    scenario.write_text("\n".join([
        "# Synthetic audio and dispatched-key verification. No human participant.",
        f"0:00:00;communications;voiceidiom;{idiom}",
        f"0:00:00;communications;voicegender;{'male' if idiom == 'english' else 'female'}",
        "0:00:00;communications;owncallsign;FAC123",
        "0:00:00;communications;othercallsign;ABC456",
        "0:00:00;communications;maxresponsedelay;12000",
        "0:00:00;sysmon;start", "0:00:00;track;start",
        "0:00:00;resman;start", "0:00:00;communications;start",
        "0:00:02;sysmon;scales-1-failure;True",
        "0:00:05;communications;radioprompt;own",
        "0:00:40;communications;radioprompt;other",
        "0:01:15;sysmon;stop", "0:01:15;track;stop",
        "0:01:15;resman;stop", "0:01:15;communications;stop",
    ]) + "\n", encoding="utf-8")
    os.environ["MATB_OPENMATB_DISPLAY_SESSION_NUMBER"] = "False"
    os.environ["MATB_EVIDENCE_IDENTITY"] = json.dumps({"execution_purpose": "practice", "condition": "SYNTHETIC_AUDIO_KEYBOARD"})
    os.chdir(runtime)
    sys.path[:0] = [str(runtime), str(root)]
    sys.argv = ["main.py", "--scenario", str(scenario), "--session-dir", str(sessions),
                "--language", args.language, "--visual-theme", "fac_modern", "--windowed", "--skip-briefing"]
    if args.briefing:
        if args.language != "es_CO":
            parser.error("--briefing requires --language es_CO")
        sys.argv.remove("--skip-briefing")
    from main import OpenMATB
    from core.scheduler import Scheduler
    from core.window import Window
    from core.logger import get_logger
    import pyglet
    from pyglet.window import key

    checks = {}
    observations = []
    observed = set()
    original_update = Scheduler.update
    tuning_key = None

    def press(symbol):
        Window.MainWindow.dispatch_event("on_key_press", symbol, 0)
        Window.MainWindow.dispatch_events()

    def release(symbol):
        Window.MainWindow.dispatch_event("on_key_release", symbol, 0)
        Window.MainWindow.dispatch_events()

    def tap(symbol):
        press(symbol)
        release(symbol)

    def observe(self, dt):
        nonlocal tuning_key
        original_update(self, dt)
        if getattr(self, "_exiting", False):
            return
        comm = self.plugins["communications"]
        win = Window.MainWindow
        if self.scenario_time > 0.5 and "radio_selection" not in checks:
            pos = comm.get_active_radio_dict()["pos"]
            symbol = key.DOWN if pos < 3 else key.UP
            tap(symbol)
            checks["radio_selection"] = comm.get_active_radio_dict()["pos"] != pos
            pump = self.plugins["resman"].parameters["pump"]["1"]
            before = pump["state"]
            tap(key.NUM_1)
            checks["pump_numeric_keyboard"] = pump["state"] != before
            tap(key.NUM_1)
            press(key.RIGHT)
            win.on_deactivate()
            checks["focus_loss_clears_held_key"] = not win.keyboard.get("RIGHT", False)
            release(key.RIGHT)
            press(key.LEFT)
            win.pause_prompt()
            checks["pause_clears_held_key"] = not win.keyboard.get("LEFT", False)
            release(key.LEFT)
            release(key.SPACE)
            checks["pause_can_resume"] = win.modal_dialog is None
        sysmon = self.plugins["sysmon"]
        if self.scenario_time > 2.2 and "sysmon_function_key" not in checks:
            gauge = sysmon.parameters["scales"]["1"]
            had_failure = gauge["_onfailure"]
            tap(key.F1)
            checks["sysmon_function_key"] = had_failure and not gauge["_onfailure"]
        active = comm._active_comm_opportunity
        if not active:
            return
        identity = active["opportunity_id"]
        if active.get("presentation_started") and identity not in observed:
            observed.add(identity)
            observations.append({"destination": active["destination"], "audio_driver": type(pyglet.media.get_audio_driver()).__name__,
                                 "playing": comm.player.playing, "duration_s": comm._last_prompt_duration_s,
                                 "voice_path": str(comm.sound_path.resolve()), "radio": active["radio"]["name"]})
        if active.get("response_window_open") and active["destination"] == "own":
            target = active["radio"]
            selected = comm.get_active_radio_dict()
            if selected["pos"] != target["pos"]:
                tap(key.DOWN if selected["pos"] < target["pos"] else key.UP)
                return
            difference = round(target["targetfreq"] - target["currentfreq"], 1)
            if abs(difference) > 0.01:
                desired = key.RIGHT if difference > 0 else key.LEFT
                if tuning_key != desired:
                    if tuning_key is not None:
                        release(tuning_key)
                    press(desired)
                    tuning_key = desired
            else:
                if tuning_key is not None:
                    release(tuning_key)
                    tuning_key = None
                checks["held_arrow_tunes_frequency"] = True
                tap(key.NUM_ENTER)
                checks["keypad_enter_confirms"] = comm._active_comm_opportunity is None
                win.switch_to()
                win.on_draw()
                pyglet.image.get_buffer_manager().get_color_buffer().save(str(out / "native-controls.png"))

    if not args.briefing:
        Scheduler.update = observe
    else:
        def inspect_briefing(_dt):
            win = Window.MainWindow
            dialog = win.modal_dialog
            checks["briefing_visible_before_task"] = dialog is not None
            dialog.play_instructions()
            checks["narration_playing"] = bool(dialog.player and dialog.player.playing)
            release(key.SPACE)
            checks["cannot_start_over_narration"] = win.modal_dialog is dialog
            win.switch_to()
            win.on_draw()
            pyglet.image.get_buffer_manager().get_color_buffer().save(str(out / "native-briefing.png"))
            release(key.Q)
            checks["exit_stops_narration"] = dialog.player is None
        pyglet.clock.schedule_once(inspect_briefing, 2)
    # Bound the diagnostic even if hardware warnings leave a modal open.
    def deadline(_dt):
        Window.MainWindow.close()
        pyglet.app.exit()
    pyglet.clock.schedule_once(deadline, 95)
    error = None
    try:
        OpenMATB()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        logger = get_logger()
        logger.close()
    events = logger.path.with_suffix(".scientific.events.jsonl")
    records = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
    opportunities = [r["payload"]["opportunity"] for r in records
                     if r.get("task") == "communications" and r.get("payload", {}).get("opportunity")]
    outcomes = [o["outcome"] for o in opportunities if o["phase"] == "closed"]
    invalid = [o for o in opportunities if o["phase"] == "invalidated"]
    passed = (error is None and len(checks) == 8 and all(checks.values()) and outcomes == ["HIT", "CR"]
              and not invalid and len(observations) == 2 and all(o["playing"] and o["audio_driver"] != "SilentDriver"
                  and Path(o["voice_path"]).parent.name == idiom for o in observations))
    if args.briefing:
        passed = error is None and len(checks) == 4 and all(checks.values()) and not opportunities
    result = {"passed": passed, "language": args.language, "synthetic": True, "physical_speaker_or_key_actuation_measured": False,
              "checks": checks, "audio": observations, "outcomes": outcomes, "invalidations": invalid, "error": error}
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
