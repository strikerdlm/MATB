# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from core.container import Container
from core.widgets.abstractwidget import *


class Light(AbstractWidget):
    def __init__(self, name: str, container: Container, label: str, color: tuple[int, int, int, int]) -> None:
        super().__init__(name, container)

        # Compute vertices
        self.border_color = VISUAL_THEME.module_color("system_monitoring", "lamp_border")
        if VISUAL_THEME.module_option("system_monitoring", "lamp_shape") == "circle":
            radius = min(self.container.w, self.container.h) * 0.34
            self.border_vertice = tuple(self.vertice_circle(self.container.get_center(), radius, 40))
            self.add_polygon("background", G(self.m_draw), self.border_vertice, color * 40)
            self.add_line_loop("border", G(self.m_draw + 1), self.border_vertice, self.border_color * 40)
            self.add_corner_marks()
        else:
            self.border_vertice = self.vertice_border(self.container)
            self.add_quad("background", G(self.m_draw), self.border_vertice, color * 4)
            self.add_lines("border", G(self.m_draw + 1), self.vertice_strip(self.border_vertice), self.border_color * 8)

        self.vertex["label"] = Label(
            label.upper(),
            font_size=F["MEDIUM"],
            x=self.container.cx,
            y=self.container.cy,
            anchor_x="center",
            anchor_y="center",
            color=C["TEXT"],
            batch=None,
            group=G(self.m_draw + 1),
            font_name=self.font_name,
        )

    def set_label(self, label: str) -> None:
        label_to_upper: str = label.upper()
        if label_to_upper == self.get_label():
            return
        self.vertex["label"].text = label_to_upper
        self.logger.record_state(self.name, "label", label_to_upper)

    def get_label(self) -> str:
        return self.vertex["label"].text

    def set_color(self, color: tuple[int, int, int, int]) -> None:
        if color == self.get_color():
            return
        background_points = len(self.on_batch["background"].colors) // 4
        self.on_batch["background"].colors[:] = color * background_points
        border_points = len(self.on_batch["border"].colors) // 4
        self.on_batch["border"].colors[:] = self.border_color * border_points

        self.logger.record_state(self.name, "background", color)
        self.logger.record_state(self.name, "border", self.border_color)

    def get_color(self) -> tuple[int, int, int, int]:
        return self.get_vertex_color("background")
