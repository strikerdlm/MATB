# Copyright 2023-2026, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from core.container import Container
from core.widgets.abstractwidget import *


class Pump(AbstractWidget):
    def __init__(
        self,
        name: str,
        container: Container,
        from_cont: Container,
        to_cont: Container,
        pump_n: int,
        color: tuple[int, int, int, int],
        pump_width: float,
        y_offset: float = 0,
    ) -> None:
        super().__init__(name, container)
        direction_vertices = self.flow_arrow_vertices(from_cont, to_cont, pump_width, y_offset)
        width: float = pump_width

        # If from_container and to_container are aligned (x or y axis)
        if from_cont.cx == to_cont.cx or from_cont.cy == to_cont.cy:
            # Draw a straight line
            self.add_lines(
                "connector_1",
                G(self.m_draw),
                (from_cont.cx, from_cont.cy + y_offset, to_cont.cx, to_cont.cy + y_offset),
                VISUAL_THEME.module_color("resource_management", "pipe_off") * 2,
            )

            # Draw the pump in the middle of the line
            x1: float = min(from_cont.cx, to_cont.cx)
            x2: float = max(from_cont.cx, to_cont.cx)
            s: int = -1 if from_cont.cx > to_cont.cx else 1
            x: float = x1 + (x2 - x1) / 2 + s * width / 2
            y: float = from_cont.cy + y_offset
            w: float = width if from_cont.cx > to_cont.cx else -width  # Pump width
            h: float = abs(w)
            self.pump_vertice: tuple[float, ...] = (x, y, x + w, y + h / 2, x + w, y - h / 2)
            self.num_location: tuple[float, float] = (x + w * 0.70, y + 2)

        else:  # If not, make an perpendicular node
            y_offset = -y_offset - 20
            self.add_lines(
                "connector_1",
                G(self.m_draw),
                (from_cont.cx, from_cont.cy, from_cont.cx, to_cont.cy + y_offset),
                VISUAL_THEME.module_color("resource_management", "pipe_off") * 2,
            )
            self.add_lines(
                "connector_2",
                G(self.m_draw),
                (to_cont.cx, to_cont.cy + y_offset, from_cont.cx, to_cont.cy + y_offset),
                VISUAL_THEME.module_color("resource_management", "pipe_off") * 2,
            )

            # And stick the pump to the source tank
            x = from_cont.cx
            y = from_cont.cy + from_cont.h / 2 + width * 2
            w = width
            self.pump_vertice = (x, y, x - w / 2, y - w, x + w / 2, y - w)
            self.num_location = (x, y - w / 2 - 3)

        # Fixed destination arrow: pump activation changes color, never direction.
        self.add_triangles("flow_direction", G(self.m_draw + 6), direction_vertices, C["TEXT"] * 3)
        self.add_triangles("triangle", G(self.m_draw + 1), self.pump_vertice, color * 3)

        pipe_color = VISUAL_THEME.module_color("resource_management", "pipe_off")
        self.add_lines("border", G(self.m_draw + 2), self.vertice_strip(self.pump_vertice), pipe_color * 6)
        if VISUAL_THEME.module_flag("resource_management", "show_pump_ring"):
            switch_radius = width * 0.72
            switch_face = self.vertice_circle(self.num_location, switch_radius, 24)
            ring = VISUAL_THEME.module_color("resource_management", "meter")
            self.add_line_loop("switch_ring", G(self.m_draw + 3), switch_face, ring * 24)

        self.vertex["label"] = Label(
            str(pump_n),
            font_size=F["SMALL"],
            font_name=self.font_name,
            x=self.num_location[0],
            y=self.num_location[1],
            anchor_x="center",
            anchor_y="center",
            color=VISUAL_THEME.palette["text"],
            group=G(self.m_draw + 2),
        )

    @staticmethod
    def flow_arrow_vertices(from_cont: Container, to_cont: Container, width: float, y_offset: float) -> tuple[float, ...]:
        direction = 1 if from_cont.cx < to_cont.cx else -1
        y = from_cont.cy + y_offset if from_cont.cy == to_cont.cy else to_cont.cy - y_offset - 20
        x = to_cont.l - 7 if direction == 1 else to_cont.l + to_cont.w + 7
        return (x, y, x - direction * 9, y + 4, x - direction * 9, y - 4)

    def set_color(self, color: tuple[int, int, int, int]) -> None:
        if color == self.get_color():
            return
        self.on_batch["triangle"].colors[:] = color * 3
        self.logger.record_state(self.name, "triangle", color)

    def set_pipe_color(self, color: tuple[int, int, int, int]) -> None:
        for name in ("connector_1", "connector_2"):
            if name in self.on_batch and self.get_vertex_color(name) != color:
                count = len(self.on_batch[name].position) // 2
                self.on_batch[name].colors[:] = color * count

    def get_color(self) -> tuple[int, int, int, int]:
        return self.get_vertex_color("triangle")
