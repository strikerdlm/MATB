# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from typing import List, Optional, Tuple

from core import validation
from plugins.abstractplugin import AbstractPlugin


class Automationhooks(AbstractPlugin):
    """Emits manual/auto switches for other plugins based on threshold triggers."""

    def __init__(self, label: str = '', taskplacement: str = 'invisible', taskupdatetime: int = 1000) -> None:
        super().__init__(label or _('Automation Hooks'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'targetplugin': validation.is_string,
        }

        self.parameters.update({
            'targetplugin': 'missiondirector',
        })

        self.rules: List[Tuple[str, str, float, str]] = []  # (plugin, metric, threshold, mode)
        self.active = False

    def start(self) -> None:
        super().start()
        self.rules = []

    # Scenario commands --------------------------------------------------
    def rule(self, payload: str) -> None:
        """
        payload: plugin,metric,threshold,mode
        Example: automationhooks;rule;payloadmanager,payload_overbandwidth,0,AUTO
        """
        parts = self._split(payload, 4)
        if not parts:
            return
        try:
            threshold = float(parts[2])
        except ValueError:
            return
        mode = parts[3].upper()
        self.rules.append((parts[0], parts[1], threshold, mode))
        self.log_performance('automation_rule', payload)

    def enable(self, payload: str) -> None:
        self.active = True
        self.log_performance('automation_enable', payload or '1')

    def disable(self, payload: str) -> None:
        self.active = False
        self.log_performance('automation_disable', payload or '1')

    # Helpers ------------------------------------------------------------
    def _split(self, payload: str, min_parts: int) -> Optional[List[str]]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',')]
        if len(parts) < min_parts:
            return None
        return parts


