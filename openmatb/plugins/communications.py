# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

import json
from math import copysign, isfinite
from pathlib import Path
from string import ascii_lowercase, ascii_uppercase, digits
from time import perf_counter_ns
from typing import Any, Callable

from pyglet.media import Player, SourceGroup, get_audio_driver, load

from core import validation
from core.constants import PATHS as P
from core.constants import REPLAY_MODE, VISUAL_THEME
from core.container import Container
from core.pseudorandom import choice, randint, uniform, xeger
from core.widgets import Radio, Simpletext
from plugins.abstractplugin import AbstractPlugin

_COMM_PRESENTATION_CEILING_S = 24.0


class Communications(AbstractPlugin):
    def __init__(self, label: str = "", taskplacement: str = "bottomleft", taskupdatetime: int = 80) -> None:
        super().__init__(_("Communications"), taskplacement, taskupdatetime)

        self.validation_dict: dict[str, Callable[..., Any] | tuple[Callable[..., Any], list[str]]] = {
            "owncallsign": validation.is_callsign,
            "othercallsign": validation.is_callsign_or_list_of,  # othercallsign can be a list of callsigns
            "voiceidiom": (validation.is_in_list, [p.name.lower() for p in P["SOUNDS"].iterdir()]),
            "voicegender": (
                validation.is_in_list,
                list(
                    set(
                        d.name.lower()
                        for idiom in P["SOUNDS"].iterdir()
                        if idiom.is_dir()
                        for d in idiom.iterdir()
                        if d.is_dir()
                    )
                ),
            ),
            "othercallsignnumber": validation.is_positive_integer,
            "airbandminMhz": validation.is_positive_float,
            "airbandmaxMhz": validation.is_positive_float,
            "airbandminvariationMhz": validation.is_positive_integer,
            "airbandmaxvariationMhz": validation.is_positive_integer,
            "radioprompt": (validation.is_in_list, ["own", "other"]),
            "promptlist": (validation.is_in_list, ["NAV_1", "NAV_2", "COM_1", "COM_2"]),
            "maxresponsedelay": validation.is_positive_integer,
            "callsignregex": validation.is_a_regex,
            "keys-selectradioup": validation.is_key,
            "keys-selectradiodown": validation.is_key,
            "keys-tunefrequencyup": validation.is_key,
            "keys-tunefrequencydown": validation.is_key,
            "keys-validateresponse": validation.is_key,
        }

        self.keys: set[str] = {"UP", "DOWN", "RIGHT", "LEFT", "ENTER"}
        self.callsign_seed: int = 1  # Useful to pseudorandomly generate different callsign when
        # trying to generate multiple callsigns at once

        self.letters: str = ascii_uppercase
        self.digits: str = digits

        # Callsign regex must be defined first because it is needed by self.get_callsign()
        self.parameters["callsignregex"] = r"[A-Z][A-Z][A-Z]\d\d\d"
        self.old_regex: str = str(self.parameters["callsignregex"])
        new_par: dict[str, Any] = dict(
            owncallsign="",
            othercallsign=list(),
            othercallsignnumber=5,
            airbandminMhz=108.0,
            airbandmaxMhz=137.0,
            airbandminvariationMhz=5,
            airbandmaxvariationMhz=6,
            voicegender="female",
            voiceidiom="spanish",
            radioprompt="",
            maxresponsedelay=20000,
            promptlist=["NAV_1", "NAV_2", "COM_1", "COM_2"],
            automaticsolver=False,
            displayautomationstate=True,
            feedbackduration=1500,
            feedbacks=dict(
                positive=dict(
                    active=False,
                    color=VISUAL_THEME.module_color("communications", "positive"),
                ),
                negative=dict(
                    active=False,
                    color=VISUAL_THEME.module_color("communications", "negative"),
                ),
            ),
            keys=dict(
                selectradioup="UP",
                selectradiodown="DOWN",
                tunefrequencyup="RIGHT",
                tunefrequencydown="LEFT",
                validateresponse="ENTER",
            ),
        )

        self.parameters.update(new_par)
        self._radioprompt_queue: list[str] = []
        self._comm_opportunity_counter: int = 0
        self._active_comm_opportunity: dict[str, Any] | None = None
        self.regenerate_callsigns()

        # Handle OWN radios information
        self.parameters["radios"] = dict()
        for r, this_radio in enumerate(self.parameters["promptlist"]):
            self.parameters["radios"][r] = {
                "name": this_radio,
                "currentfreq": self.get_rand_frequency(r),
                "targetfreq": None,
                "pos": r,
                "response_time": 0,
                "is_active": False,
                "is_prompting": False,
                "_feedbacktimer": None,
                "_feedbacktype": None,
            }
        self.lastradioselected: int | None = None
        self.frequency_modulation: float = 0.1
        self.sound_path: Path | None = None

        self.set_sample_sounds()

        self.automode_position: tuple[float, float] = (0.5, 0.2)

    def get_sounds_path(self) -> Path:
        return P["SOUNDS"].joinpath(self.parameters["voiceidiom"], self.parameters["voicegender"])

    def set_sample_sounds(self) -> None:
        new_path: Path = self.get_sounds_path()
        if new_path == self.sound_path:
            return

        if not new_path.exists():
            # Do not keep the previous language bank after an invalid selection.
            self.sound_path = None
            raise RuntimeError(f"COMM voice bank unavailable: {new_path}. Check voiceidiom/voicegender.")

        self.sound_path = new_path
        self.samples_path: list[Path] = [
            self.sound_path.joinpath(f"{i}.wav")
            for i in [s for s in digits + ascii_lowercase]
            + [this_radio.lower() for this_radio in self.parameters["promptlist"]]
            + ["radio", "point", "frequency", "empty"]
        ]

        missing = [sample for sample in self.samples_path if not sample.is_file()]
        if missing:
            self.sound_path = None
            raise RuntimeError(f"COMM audio samples unavailable: {', '.join(str(p) for p in missing[:3])}")

    def regenerate_callsigns(self) -> None:
        self.parameters["owncallsign"] = self.get_callsign()
        for _i in range(self.parameters["othercallsignnumber"]):
            this_callsign: str = self.get_callsign()
            while this_callsign in [self.parameters["owncallsign"]] + self.parameters["othercallsign"]:
                this_callsign = self.get_callsign()
            self.parameters["othercallsign"].append(this_callsign)

    def create_widgets(self) -> None:
        super().create_widgets()
        self.add_widget(
            "callsign",
            Simpletext,
            container=self.task_container,
            text=_("Callsign \t\t %s") % self.parameters["owncallsign"],
            y=0.9,
        )

        active_index: int = randint(0, len(self.parameters["radios"]) - 1, self.alias, self.scenario_time)
        for pos, radio in self.parameters["radios"].items():
            radio["is_active"] = pos == active_index
            # Compute radio container
            radio_container: Container = Container(
                radio["name"],
                self.task_container.l,
                self.task_container.b + self.task_container.h * (0.7 - 0.13 * pos),
                self.task_container.w,
                self.task_container.h * 0.1,
            )

            radio["widget"] = self.add_widget(
                f"radio_{radio['name']}",
                Radio,
                container=radio_container,
                label=radio["name"],
                frequency=radio["currentfreq"],
                on=radio["is_active"],
            )

    def pause(self) -> None:
        super().pause()
        if hasattr(self, "player"):
            self.player.pause()

    def resume(self) -> None:
        super().resume()
        if hasattr(self, "player") and self.player.source is not None:
            self.player.play()

    def get_callsign(self) -> str:
        self.callsign_seed += 1
        call_rgx: str = self.parameters["callsignregex"]
        duplicateChar: bool = True
        notInList: bool = True

        self.letters = ascii_uppercase if len(self.letters) < 3 else self.letters
        self.digits = digits if len(self.digits) < 3 else self.digits

        while duplicateChar or notInList:
            callsign: str = xeger(call_rgx, self.alias, self.scenario_time, self.callsign_seed)
            duplicateChar = len(callsign) != len(set(callsign))
            notInList = any([s not in self.letters + self.digits for s in callsign])
            self.callsign_seed += 1

        for s in callsign:
            for li in [self.letters, self.digits]:
                if s in li:
                    li = li.replace(s, "")
        return callsign

    def _prompt_sound_ids(self, callsign: str, radio_name: str, freq: float) -> list[str]:
        contextual_radio = f"{radio_name.lower()}_frequency"
        contextual_path = self.sound_path.joinpath(f"{contextual_radio}.wav")
        radio_instruction = (
            [contextual_radio]
            if contextual_path.is_file()
            else ["radio", radio_name.lower(), "frequency"]
        )
        return (
            ["empty"] * 20
            + [c.lower() for c in callsign]
            + [c.lower() for c in callsign]
            + radio_instruction
            + [c.lower().replace(".", "point") for c in str(freq)]
            + ["empty"]
        )

    def group_audio_files(self, callsign: str, radio_name: str, freq: float) -> Any:
        list_of_sounds = self._prompt_sound_ids(callsign, radio_name, freq)

        sources: list[Any] = []
        failed_paths: list[str] = []
        total_duration_s = 0.0
        for f in list_of_sounds:
            wav_path = self.sound_path.joinpath(f"{f}.wav")
            try:
                source: Any = load(str(wav_path), streaming=False)
                duration_s = float(source.duration)
                if not isfinite(duration_s) or duration_s < 0:
                    raise ValueError("audio source has no finite non-negative duration")
                total_duration_s += duration_s
                sources.append(source)
            except Exception:  # noqa: BLE001 - converted to invalid trial evidence below
                failed_paths.append(str(wav_path))

        if failed_paths or len(sources) != len(list_of_sounds):
            raise RuntimeError(
                "audio prompt assets missing or unreadable: " + ", ".join(failed_paths[:3])
            )
        if (
            not isfinite(total_duration_s)
            or total_duration_s <= 0
            or total_duration_s > _COMM_PRESENTATION_CEILING_S
        ):
            raise RuntimeError(
                "audio prompt duration is unavailable or exceeds the qualified 24-second ceiling"
            )
        self._last_prompt_duration_s = total_duration_s

        group: Any = SourceGroup()
        for source in sources:
            group.add(source)
        return group

    def _log_opportunity(self, opportunity: dict[str, Any], phase: str, **details: Any) -> None:
        payload = {
            "schema_version": "1.0",
            "opportunity_id": opportunity["opportunity_id"],
            "destination": opportunity["destination"],
            "automation_active": bool(opportunity["automation_active"]),
            "phase": phase,
            **details,
        }
        self.log_performance(
            "comm_opportunity_v1",
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False),
        )

    def _new_opportunity(self, destination: str) -> dict[str, Any]:
        self._comm_opportunity_counter = getattr(self, "_comm_opportunity_counter", 0) + 1
        opportunity = {
            "opportunity_id": f"comm-{self._comm_opportunity_counter:06d}",
            "destination": destination,
            "automation_active": bool(self.parameters.get("automaticsolver", False)),
            "presentation_started": False,
            "response_window_open": False,
            "response_time_ms": 0,
            "radio": None,
        }
        self._log_opportunity(opportunity, "opened")
        return opportunity

    def _invalidate_opportunity(
        self, opportunity: dict[str, Any], reason: str, **details: Any
    ) -> None:
        self._log_opportunity(opportunity, "invalidated", reason=reason, **details)
        if getattr(self, "_active_comm_opportunity", None) is opportunity:
            radio = opportunity.get("radio")
            if isinstance(radio, dict):
                radio["is_prompting"] = False
                self.disable_radio_target(radio)
            self._active_comm_opportunity = None

    def _close_active_opportunity(
        self,
        outcome: str,
        response_time_ms: float | None,
        *,
        response_classification: str | None = None,
        response_actor: str | None = None,
    ) -> None:
        opportunity = getattr(self, "_active_comm_opportunity", None)
        if opportunity is None:
            return
        details: dict[str, Any] = {
            "outcome": outcome,
            "response_time_ms": response_time_ms,
            "response_actor": (
                response_actor
                if response_actor is not None
                else (
                    "automation"
                    if opportunity["automation_active"]
                    else "participant"
                )
            ),
        }
        if details["response_actor"] not in {"participant", "automation"}:
            raise ValueError("COMM response actor must be participant or automation")
        if response_classification is not None:
            details["response_classification"] = response_classification
        details.update({
            "closed_scenario_time_s": self.scenario_time,
            "response_window_opened_scenario_time_s": opportunity.get(
                "response_window_opened_scenario_time_s"
            ),
            "response_deadline_s": opportunity.get("response_deadline_s"),
            "close_lateness_tolerance_ms": int(self.parameters["taskupdatetime"]),
        })
        self._log_opportunity(opportunity, "closed", **details)
        self._active_comm_opportunity = None

    def _open_response_window(self, *, opening_lateness_ms: int = 0) -> None:
        opportunity = getattr(self, "_active_comm_opportunity", None)
        if opportunity is None or opportunity["response_window_open"]:
            return
        opened_s = float(self.scenario_time)
        deadline_s = opened_s + int(self.parameters["maxresponsedelay"]) / 1000.0
        opportunity["response_window_open"] = True
        opportunity["response_time_ms"] = 0
        opportunity["response_window_opened_scenario_time_s"] = opened_s
        opportunity["response_deadline_s"] = deadline_s
        radio = opportunity.get("radio")
        if opportunity["destination"] == "own" and isinstance(radio, dict):
            radio["response_time"] = 0
            radio["_response_window_opened_scenario_time_s"] = opened_s
            radio["_response_deadline_s"] = deadline_s
        self._log_opportunity(
            opportunity,
            "response_window_opened",
            opened_scenario_time_s=opened_s,
            deadline_s=deadline_s,
            opening_lateness_ms=opening_lateness_ms,
            close_lateness_tolerance_ms=int(self.parameters["taskupdatetime"]),
        )

    def _complete_presentation_if_ready(self) -> None:
        opportunity = getattr(self, "_active_comm_opportunity", None)
        if (
            opportunity is None
            or not opportunity.get("presentation_started")
            or opportunity.get("response_window_open")
            or getattr(self, "player", None) is None
            or self.player.source is not None
        ):
            return
        expected_end = opportunity.get("presentation_expected_end_scenario_time_s")
        if not isinstance(expected_end, (int, float)) or not isfinite(float(expected_end)):
            self._invalidate_opportunity(
                opportunity, "presentation_timing_evidence_unavailable"
            )
            return
        timing_error_ms = round(
            (self.scenario_time - float(expected_end)) * 1000
        )
        tolerance_ms = int(self.parameters["taskupdatetime"])
        if abs(timing_error_ms) > tolerance_ms:
            early_completion = timing_error_ms < 0
            self._invalidate_opportunity(
                opportunity,
                (
                    "presentation_completed_before_expected_duration"
                    if early_completion
                    else "response_window_opened_after_update_stall"
                ),
                expected_end_scenario_time_s=float(expected_end),
                observed_completion_scenario_time_s=self.scenario_time,
                timing_error_ms=timing_error_ms,
                lateness_ms=max(0, timing_error_ms),
                earliness_ms=max(0, -timing_error_ms),
                lateness_tolerance_ms=tolerance_ms,
            )
            return
        prompted_radio = opportunity.get("radio")
        if opportunity["destination"] == "own" and prompted_radio is not None:
            prompted_radio["is_prompting"] = False
            self.logger.log_manual_entry(
                f"Target {prompted_radio['name']}:{prompted_radio['targetfreq']}"
            )
        self._open_response_window(opening_lateness_ms=max(0, timing_error_ms))

    def _update_active_response_timing(self) -> None:
        opportunity = getattr(self, "_active_comm_opportunity", None)
        if opportunity is None or not opportunity.get("response_window_open"):
            return
        opened_s = opportunity.get("response_window_opened_scenario_time_s")
        deadline_s = opportunity.get("response_deadline_s")
        if not all(
            isinstance(value, (int, float)) and isfinite(float(value))
            for value in (opened_s, deadline_s)
        ):
            self._invalidate_opportunity(
                opportunity, "response_window_timing_evidence_unavailable"
            )
            return
        elapsed_ms = max(0, round((self.scenario_time - float(opened_s)) * 1000))
        opportunity["response_time_ms"] = elapsed_ms
        radio = opportunity.get("radio")
        if opportunity["destination"] == "own" and isinstance(radio, dict):
            radio["response_time"] = elapsed_ms
        if self.scenario_time < float(deadline_s):
            return
        lateness_ms = max(0, round((self.scenario_time - float(deadline_s)) * 1000))
        tolerance_ms = int(self.parameters["taskupdatetime"])
        if lateness_ms > tolerance_ms:
            self._invalidate_opportunity(
                opportunity,
                "response_window_closed_after_update_stall",
                deadline_s=float(deadline_s),
                observed_close_scenario_time_s=self.scenario_time,
                lateness_ms=lateness_ms,
                lateness_tolerance_ms=tolerance_ms,
            )
            return
        if opportunity["destination"] == "other":
            self.log_performance("response_time", float("nan"))
            self.log_performance("sdt_value", "CR")
            self._close_active_opportunity("CR", None)
        elif isinstance(radio, dict):
            self.record_target_missing(radio)

    def prompt_for_a_new_target(
        self,
        destination: str,
        radio_name: str,
        opportunity: dict[str, Any],
    ) -> bool:
        preparation_started_ns = perf_counter_ns()
        self.parameters["radioprompt"] = ""
        radio: dict[str, Any] = self.get_radios_by_key_value("name", radio_name)[0]
        radio_n: int = self.get_radios_number_by_key_value("name", radio_name)[0]

        callsign: str | list[str] = self.parameters[f"{destination}callsign"]
        callsign = choice(callsign, self.alias, self.scenario_time, radio_n) if isinstance(callsign, list) else callsign

        random_frequency: float = self.get_rand_frequency(radio_n)
        while not (
            self.parameters["airbandminvariationMhz"]
            < abs(random_frequency - radio["currentfreq"])
            < self.parameters["airbandmaxvariationMhz"]
        ):
            radio_n += 15
            random_frequency = self.get_rand_frequency(radio_n)

        try:
            driver = get_audio_driver()
            if driver is None or type(driver).__name__ == "SilentDriver":
                raise RuntimeError("No audible output device is available (silent audio backend)")
            sound_group: Any = self.group_audio_files(callsign, radio_name, random_frequency)
            prompt_duration_s = float(getattr(self, "_last_prompt_duration_s"))
            if (
                not isfinite(prompt_duration_s)
                or prompt_duration_s <= 0
                or prompt_duration_s > _COMM_PRESENTATION_CEILING_S
            ):
                raise RuntimeError("prompt duration is outside the qualified timing profile")
            self.player: Any = Player()
            self.player.queue(sound_group)
            self.player.play()
            play_returned_ns = perf_counter_ns()
        except Exception as exc:  # noqa: BLE001 - evidence must survive media backend failures
            self.logger.log_manual_entry(f"Audio prompt playback failed: {type(exc).__name__}: {exc}")
            self._invalidate_opportunity(opportunity, "presentation_failed")
            # Continuing would score unheard calls as participant omissions.
            # The scheduler records the failure and stops the session.
            raise RuntimeError(
                "COMM audio unavailable. Check the Windows output device, application volume "
                "and headphones before starting a new practice block."
            ) from exc

        if destination == "own":
            radio["targetfreq"] = random_frequency
            radio["is_prompting"] = True
        # WAV decoding and backend creation happen synchronously within this
        # scheduler tick. Anchor playback after that preparation, otherwise the
        # first prompt's load time is mistaken for late audio completion.
        preparation_duration_s = (play_returned_ns - preparation_started_ns) / 1_000_000_000
        presentation_start_s = self.scenario_time + preparation_duration_s
        opportunity["presentation_started"] = True
        opportunity["radio"] = radio
        opportunity["presentation_started_scenario_time_s"] = presentation_start_s
        opportunity["presentation_expected_end_scenario_time_s"] = (
            presentation_start_s + prompt_duration_s
        )
        self._log_opportunity(
            opportunity,
            "presentation_started",
            radio_name=radio_name,
            software_play_invoked=True,
            audio_driver=type(driver).__name__,
            physical_onset_measured=False,
            expected_duration_s=prompt_duration_s,
            started_scenario_time_s=presentation_start_s,
            expected_end_scenario_time_s=presentation_start_s + prompt_duration_s,
            preparation_duration_s=preparation_duration_s,
            play_returned_monotonic_ns=play_returned_ns,
            completion_lateness_tolerance_ms=int(self.parameters["taskupdatetime"]),
        )
        return True

    def set_parameter(self, keys_str: str, value: Any) -> dict[str, Any]:
        if keys_str == "radioprompt" and str(value).lower() in {"own", "other"}:
            destination = str(value).lower()
            context = getattr(self, "_scenario_dispatch_context", None)
            scheduled = (
                context.get("scheduled_time_s")
                if isinstance(context, dict)
                else None
            )
            if (
                isinstance(scheduled, (int, float))
                and not isinstance(scheduled, bool)
                and isfinite(float(scheduled))
                and (self.scenario_time - float(scheduled)) * 1000
                > int(self.parameters["taskupdatetime"])
            ):
                opportunity = self._new_opportunity(destination)
                self._invalidate_opportunity(
                    opportunity,
                    "prompt_command_dispatched_after_observable_onset",
                    scheduled_scenario_time_s=float(scheduled),
                    dispatch_scenario_time_s=self.scenario_time,
                    source_line=context.get("source_line"),
                )
                return super().set_parameter(keys_str, "")
            self._radioprompt_queue = getattr(self, "_radioprompt_queue", [])
            self._radioprompt_queue.append(destination)
            return super().set_parameter(keys_str, "")
        return super().set_parameter(keys_str, value)

    def _handle_radioprompt(self, destination: str) -> None:
        opportunity = self._new_opportunity(destination)
        if getattr(self, "_active_comm_opportunity", None) is not None:
            self._invalidate_opportunity(opportunity, "prior_opportunity_active")
            return
        radio_name_to_prompt: str | None = None

        if destination == "own":
            non_target_radios: list[dict[str, Any]] = self.get_non_target_radios_list()
            if len(non_target_radios) > 0:
                # Random choices are written to the scientific JSONL stream.
                # Select the stable name, not a dict containing a live Radio widget.
                # Retaining candidate order and seed preserves the selected radio.
                radio_name_to_prompt = choice(
                    [radio["name"] for radio in non_target_radios],
                    self.alias, self.scenario_time, 1,
                )
        elif destination == "other":
            radio_name_to_prompt = choice(
                self.parameters["promptlist"], self.alias, self.scenario_time, 1
            )

        if radio_name_to_prompt is not None:
            self._active_comm_opportunity = opportunity
            self.prompt_for_a_new_target(destination, radio_name_to_prompt, opportunity)
        else:
            self._invalidate_opportunity(opportunity, "no_eligible_radio")
            self.logger.log_manual_entry("Error. Could not trigger prompt")

    def get_rand_frequency(self, radio_n: int) -> float:
        return round(
            uniform(
                float(self.parameters["airbandminMhz"]),
                float(self.parameters["airbandmaxMhz"]),
                self.alias,
                self.scenario_time,
                radio_n,
            ),
            1,
        )

    def get_target_radios_list(self) -> list[dict[str, Any]]:
        # Multiple radios can have a target frequency at the same time
        # because of a potential delay in reactions
        return [r for _, r in self.parameters["radios"].items() if r["targetfreq"] is not None]

    def get_non_target_radios_list(self) -> list[dict[str, Any]]:
        # Multiple radios can have a target frequency at the same time
        # because of a potential delay in reactions
        return [r for _, r in self.parameters["radios"].items() if r["targetfreq"] is None]

    def get_active_radio_dict(self) -> dict[str, Any] | None:
        radio: list[dict[str, Any]] | None = self.get_radios_by_key_value("is_active", True)
        if radio is not None:
            return radio[0]

    def get_radio_dict_by_pos(self, pos: int | float) -> dict[str, Any] | None:
        radio: list[dict[str, Any]] | None = self.get_radios_by_key_value("pos", pos)
        if radio is not None:
            return radio[0]

    def get_radios_by_key_value(self, k: str, v: Any) -> list[dict[str, Any]] | None:
        radio_list: list[dict[str, Any]] = [r for _, r in self.parameters["radios"].items() if r[k] == v]
        if len(radio_list) > 0:
            return radio_list

    def get_radios_number_by_key_value(self, k: str, v: Any) -> list[int] | None:
        num_list: list[int] = [i for i, r in self.parameters["radios"].items() if r[k] == v]
        if len(num_list) > 0:
            return num_list

    def get_response_timers(self) -> list[int]:
        return [r["response_time"] for _, r in self.parameters["radios"].items() if r["response_time"] > 0]

    def get_waiting_response_radios(self) -> list[dict[str, Any]]:
        """A radio is waiting a response when it specifies a target and its prompting message
        is over"""

        return [
            r
            for _, r in self.parameters["radios"].items()
            if r in self.get_target_radios_list() and not r["is_prompting"]
        ]

    def get_max_pos(self) -> int:
        return max([r["pos"] for k, r in self.parameters["radios"].items()])

    def get_min_pos(self) -> int:
        return min([r["pos"] for k, r in self.parameters["radios"].items()])

    def modulate_frequency(self) -> None:
        if self.is_key_state(self.parameters["keys"]["tunefrequencydown"], True):
            self.get_active_radio_dict()["currentfreq"] -= self.frequency_modulation
        elif self.is_key_state(self.parameters["keys"]["tunefrequencyup"], True):
            self.get_active_radio_dict()["currentfreq"] += self.frequency_modulation

    def compute_next_plugin_state(self) -> None:
        if self.is_paused():
            return
        # Audio completion and response deadlines must be observed every frame.
        # Throttling these to the radio-control update can consume the entire
        # lateness allowance before the next ordinary update is even due.
        self._complete_presentation_if_ready()
        self._update_active_response_timing()
        if not super().compute_next_plugin_state():
            return

        if self.parameters["callsignregex"] != self.old_regex:
            self.regenerate_callsigns()
            self.old_regex = str(self.parameters["callsignregex"])

        self.set_sample_sounds()  # Check if sounds path has been renewed

        direct_prompt = str(self.parameters.get("radioprompt") or "").lower()
        if direct_prompt in {"own", "other"}:
            self._radioprompt_queue = getattr(self, "_radioprompt_queue", [])
            self._radioprompt_queue.append(direct_prompt)
            self.parameters["radioprompt"] = ""
        queued_prompts = list(getattr(self, "_radioprompt_queue", []))
        self._radioprompt_queue = []
        for index, prompt in enumerate(queued_prompts):
            if index == 0:
                self._handle_radioprompt(prompt)
            else:
                self._invalidate_opportunity(
                    self._new_opportunity(prompt),
                    "multiple_prompts_dispatched_in_one_update",
                )

        if self.can_receive_keys:
            self.modulate_frequency()

        active: dict[str, Any] = self.get_active_radio_dict()

        # If multiple radios must be modified
        # The automatic solver sticks to the first one (until it is tuned)
        if self.parameters["automaticsolver"] is True and not REPLAY_MODE:
            waiting_radios: list[dict[str, Any]] = self.get_waiting_response_radios()

            # Only if a radio is waiting autosolving, do it
            if len(waiting_radios) > 0:
                autoradio: dict[str, Any] = waiting_radios[0]

                if active != autoradio:  # Automatic radio switch if needed
                    active["is_active"] = False
                    current_index: int = active["pos"]
                    target_index: int = autoradio["pos"]
                    new_index: float = current_index + copysign(1, target_index - current_index)
                    self.get_radio_dict_by_pos(new_index)["is_active"] = True

                # Automatic radio tune
                elif active["targetfreq"] != active["currentfreq"]:
                    active["currentfreq"] = round(
                        active["currentfreq"] + copysign(0.1, active["targetfreq"] - active["currentfreq"]), 1
                    )
                else:
                    self.confirm_response(
                        response_actor="automation"
                    )  # Emulate a response confirmation

        active["currentfreq"] = self.keep_value_between(
            active["currentfreq"], up=self.parameters["airbandmaxMhz"], down=self.parameters["airbandminMhz"]
        )

        # Feedback handling
        for _r, radio in self.parameters["radios"].items():
            if radio["_feedbacktimer"] is not None:
                radio["_feedbacktimer"] -= self.parameters["taskupdatetime"]
                if radio["_feedbacktimer"] <= 0:
                    radio["_feedbacktimer"] = None
                    radio["_feedbacktype"] = None

    def refresh_widgets(self) -> None:
        if not super().refresh_widgets():
            return

        self.widgets["communications_callsign"].set_text(self.parameters["owncallsign"])

        # Move arrow to active radio
        for _, radio in self.parameters["radios"].items():
            if not radio["is_active"] and radio["widget"].is_selected:
                radio["widget"].hide_arrows()
            elif radio["is_active"] and not radio["widget"].is_selected:
                radio["widget"].show_arrows()

            # Propagate current frequencies values to the widgets
            radio["widget"].set_frequency_text(radio["currentfreq"])

            # ... also check a need for feedback refreshing
            if radio["_feedbacktimer"] is not None:
                color: tuple[int, ...] = self.parameters["feedbacks"][radio["_feedbacktype"]]["color"]
            else:
                color = VISUAL_THEME.module_color("communications", "panel")
            radio["widget"].set_feedback_color(color)

    def disable_radio_target(self, radio: dict[str, Any]) -> None:
        radio["response_time"] = 0
        radio["targetfreq"] = None
        radio.pop("_response_window_opened_scenario_time_s", None)
        radio.pop("_response_deadline_s", None)

    def record_target_missing(self, target_radio: dict[str, Any]) -> None:
        self.log_performance("target_radio", target_radio["name"])
        self.log_performance("target_frequency", target_radio["targetfreq"])
        self.log_performance("response_was_needed", True)
        self.log_performance("responded_radio", float("nan"))
        self.log_performance("responded_frequency", float("nan"))
        self.log_performance("correct_radio", False)
        self.log_performance("response_deviation", float("nan"))
        self.log_performance("response_time", float("nan"))
        self.log_performance("sdt_value", "MISS")
        self._close_active_opportunity("MISS", None)

        self.disable_radio_target(target_radio)

        self.set_feedback(target_radio, ft="negative")

    def get_sdt_value(
        self, response_needed: bool, was_a_radio_responded: bool, correct_radio: bool | float, response_deviation: float
    ) -> str | None:
        if not response_needed:
            return "FA"
        elif was_a_radio_responded is False:
            return "MISS"
        elif correct_radio and response_deviation == 0:
            return "HIT"
        elif correct_radio is False and response_deviation == 0:
            return "BAD_RADIO"
        elif response_deviation != 0 and correct_radio:
            return "BAD_FREQ"
        elif correct_radio is False and response_deviation != 0:
            return "BAD_RADIO_FREQ"

    def confirm_response(self, *, response_actor: str = "participant") -> None:
        """Evaluate response performance and log it"""

        opportunity = getattr(self, "_active_comm_opportunity", None)
        if opportunity is not None and not opportunity.get("response_window_open"):
            self.logger.log_manual_entry("COMM response ignored during audio presentation")
            return
        if opportunity is not None:
            self._update_active_response_timing()
            if getattr(self, "_active_comm_opportunity", None) is not opportunity:
                self.logger.log_manual_entry(
                    "COMM response ignored after response-window closure"
                )
                return

        # Retrieve the responded radio and the target radios
        responded_radio: dict[str, Any] = self.get_active_radio_dict()
        waiting_radios: list[dict[str, Any]] = self.get_waiting_response_radios()

        # Check if there was a target to be responded to
        response_needed: bool = len(waiting_radios) > 0

        # Check if the responded radio was prompting (good radio)
        good_radio: bool | float = responded_radio in waiting_radios if len(waiting_radios) else float("nan")

        # If a target radio is responded, get it to compute response deviation and time
        # If not, get the target radio only if it is single
        # (if there were two target radios simultaneously, we can't decide which to select
        #  to compute deviation and response time with the uncorrect responded radio)
        measure_radio: dict[str, Any] | None
        if responded_radio in waiting_radios:
            measure_radio = responded_radio
        elif len(waiting_radios) == 1:
            measure_radio = waiting_radios[0]
        else:
            measure_radio = None

        # Now compute
        deviation: float
        rt: int | float
        target_frequency: float | None
        target_radio_name: str | float
        if measure_radio is not None:
            target_frequency = measure_radio["targetfreq"]
            target_radio_name = measure_radio["name"]
            deviation = round(responded_radio["currentfreq"] - target_frequency, 1)
            rt = measure_radio["response_time"]
        else:
            deviation = rt = target_frequency = target_radio_name = float("nan")

        sdt: str | None = self.get_sdt_value(response_needed, True, good_radio, deviation)

        self.log_performance("response_was_needed", response_needed)
        self.log_performance("target_radio", target_radio_name)
        self.log_performance("responded_radio", responded_radio["name"])
        self.log_performance("target_frequency", target_frequency)
        self.log_performance("responded_frequency", responded_radio["currentfreq"])
        self.log_performance("correct_radio", good_radio)
        self.log_performance("response_deviation", deviation)
        self.log_performance("response_time", rt)
        self.log_performance("sdt_value", sdt)
        if opportunity is not None and sdt is not None:
            # Signal-detection outcome and response-accuracy classification are
            # distinct. An incorrect tune after an OWN prompt is a valid MISS,
            # not an invalid opportunity; retain the richer legacy class too.
            observed_outcome = (
                "HIT"
                if sdt == "HIT"
                else "MISS"
                if opportunity["destination"] == "own"
                else "FA"
            )
            lifecycle_rt = (
                opportunity.get("response_time_ms")
                if opportunity["destination"] == "other"
                else rt
            )
            self._close_active_opportunity(
                observed_outcome,
                float(lifecycle_rt)
                if isinstance(lifecycle_rt, (int, float)) and lifecycle_rt == lifecycle_rt
                else None,
                response_classification=sdt,
                response_actor=response_actor,
            )

        # Response is good if both radio and frequency are correct
        if not response_needed:
            self.set_feedback(responded_radio, ft="negative")
        else:
            if measure_radio is not None:
                # One participant validation closes one opportunity. Prevent a
                # later timeout from adding a second outcome to the same trial.
                self.disable_radio_target(measure_radio)
            if good_radio and deviation == 0:
                self.set_feedback(responded_radio, ft="positive")
            else:
                self.set_feedback(responded_radio, ft="negative")

    def set_feedback(self, radio: dict[str, Any], ft: str) -> None:
        # Set the feedback type and duration, if the gauge has got one
        # (the feedback widget is refreshed by the refresh_widget method)
        if self.parameters["feedbacks"][ft]["active"]:
            radio["_feedbacktype"] = ft
            radio["_feedbacktimer"] = self.parameters["feedbackduration"]

    def do_on_key(self, key: str, state: str, emulate: bool) -> None:
        """Check for radio change and frequency validation"""
        if key == "NUM_ENTER" and self.parameters["keys"]["validateresponse"] == "ENTER":
            key = "ENTER"
        key = super().do_on_key(key, state, emulate)
        if key is None:
            return

        if state == "press":
            change_radio: int = 0
            if key == self.parameters["keys"]["selectradioup"]:
                change_radio = -1
            elif key == self.parameters["keys"]["selectradiodown"]:
                change_radio = 1

            if change_radio != 0:
                next_active_n: int | float = self.keep_value_between(
                    self.get_active_radio_dict()["pos"] + change_radio, down=self.get_min_pos(), up=self.get_max_pos()
                )

                self.get_active_radio_dict()["is_active"] = False
                self.get_radio_dict_by_pos(next_active_n)["is_active"] = True

            elif key == self.parameters["keys"]["validateresponse"]:
                self.confirm_response(
                    response_actor="automation" if emulate else "participant"
                )

    def stop(self) -> None:
        queued_prompts = list(getattr(self, "_radioprompt_queue", []))
        self._radioprompt_queue = []
        for destination in queued_prompts:
            opportunity = self._new_opportunity(destination)
            self._invalidate_opportunity(
                opportunity,
                "task_stopped_before_presentation",
            )
        opportunity = getattr(self, "_active_comm_opportunity", None)
        if opportunity is not None:
            radio = opportunity.get("radio")
            if isinstance(radio, dict) and radio.get("targetfreq") is not None:
                self.disable_radio_target(radio)
            self._invalidate_opportunity(opportunity, "task_stopped_before_outcome")
        player = getattr(self, "player", None)
        cleanup_error: Exception | None = None
        if player is not None:
            try:
                pause = getattr(player, "pause", None)
                if callable(pause):
                    pause()
            except Exception as exc:  # noqa: BLE001 - still attempt device release
                cleanup_error = exc
            try:
                delete = getattr(player, "delete", None)
                if callable(delete):
                    delete()
            except Exception as exc:  # noqa: BLE001 - surface after lifecycle closure
                cleanup_error = cleanup_error or exc
        super().stop()
        if cleanup_error is not None:
            raise RuntimeError("COMM audio backend cleanup failed") from cleanup_error
