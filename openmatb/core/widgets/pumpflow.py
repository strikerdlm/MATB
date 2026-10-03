# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from core.container import Container
from core.widgets.abstractwidget import *


class PumpFlow(AbstractWidget):
    def __init__(self, name: str, container: Container, label: str, flow: int, route: str = "") -> None:
        super().__init__(name, container)

        self.label: str = label
        self.flow: int = flow
        self.displayed_flow = 0

        # Pump label #
        self.vertex[self.label] = Label(
            self.label,
            font_size=F["SMALL"],
            font_name=self.font_name,
            x=self.container.l + self.container.w * 0.175,
            y=self.container.cy,
            anchor_x="left",
            anchor_y="center",
            color=C["TEXT"],
            group=G(self.m_draw + 1),
        )

        for key, text, x, anchor in (("route", route, 0.285, "left"), ("rate", "0", 0.672, "right")):
            self.vertex[key] = Label(text, font_size=F["SMALL"], font_name=self.font_name,
                x=self.container.l + self.container.w * x, y=self.container.cy,
                anchor_x=anchor, anchor_y="center", color=C["TEXT"], group=G(self.m_draw + 1))

    def pump_string(self, value: int) -> str:
        return f"{self.label}\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t{value}"

    def set_flow(self, flow: int) -> None:
        if self.pump_string(flow) == self.get_flow():
            return
        self.displayed_flow = flow
        self.vertex["rate"].text = str(flow)
        self.logger.record_state(self.name, self.label, flow)

    def get_flow(self) -> str:
        return self.pump_string(self.displayed_flow)
