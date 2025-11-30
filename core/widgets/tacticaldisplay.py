# Copyright 2023-2024, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)
#
# TacticalDisplay widget implementation
# Implementation Credit: Dr Diego Malpica, Aerospace Medicine

"""
TacticalDisplay: A 2D tactical overlay widget for OpenMATB.

Provides a lightweight 2D visualization for:
- Geofence polygon boundaries
- UAV/entity positions as simple icons
- Status highlighting (breach indicators, selected entities)

Reference: Manual.md Section 2.5 - Minimal 2D Tactical Overlays
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pyglet.gl import GL_LINES, GL_POLYGON, GL_TRIANGLES
from pyglet.text import Label

from core.constants import COLORS as C
from core.constants import FONT_SIZES as F
from core.constants import STATUS_COLORS
from core.constants import Group as G
from core.widgets.abstractwidget import AbstractWidget

if TYPE_CHECKING:
    from core.container import Container


@dataclass(frozen=True, slots=True)
class TacticalEntity:
    """Immutable representation of an entity on the tactical display.

    Attributes:
        entity_id: Unique identifier for the entity (e.g., 'UAV1', 'INTRUDER_01').
        x_norm: Normalized X position (0.0 to 1.0 within display bounds).
        y_norm: Normalized Y position (0.0 to 1.0 within display bounds).
        icon_type: Shape type - 'diamond', 'circle', 'triangle', 'square'.
        status: Entity status - 'NORMAL', 'WARNING', 'CRITICAL', 'DISABLED'.
        label: Optional text label to display near the entity.
        heading_deg: Optional heading in degrees (0=North, 90=East).
    """

    entity_id: str
    x_norm: float
    y_norm: float
    icon_type: str = "diamond"
    status: str = "NORMAL"
    label: str | None = None
    heading_deg: float | None = None


# Maximum entities to prevent unbounded memory growth
MAX_ENTITIES: int = 50
MAX_POLYGON_POINTS: int = 100


class TacticalDisplay(AbstractWidget):
    """A 2D tactical overlay widget for displaying geofences and entity positions.

    This widget renders a simplified top-down view suitable for:
    - Sense-and-Avoid geofence visualization
    - Swarm formation position display
    - VTOL pad and launch/recovery point markers

    All positions use normalized coordinates (0.0 to 1.0) mapped to the
    widget container bounds. The widget stays strictly 2D with no depth cues.

    Attributes:
        entities: Dictionary of entity_id -> TacticalEntity.
        geofence_points: List of (x_norm, y_norm) tuples defining the geofence polygon.
        show_grid: Whether to display background grid lines.
        icon_size: Size of entity icons as fraction of container width.
    """

    __slots__ = (
        "_entities",
        "_geofence_points",
        "_show_grid",
        "_icon_size",
        "_entity_labels",
        "_breach_entities",
        "_title_label",
    )

    def __init__(
        self,
        name: str,
        container: Container,
        show_grid: bool = True,
        icon_size: float = 0.04,
        title: str | None = None,
        draw_order: int = 1,
    ) -> None:
        """Initialize the tactical display widget.

        Args:
            name: Widget identifier.
            container: The container defining the display bounds.
            show_grid: Whether to show background grid lines. Defaults to True.
            icon_size: Entity icon size as fraction of container width. Defaults to 0.04.
            title: Optional title label for the display.
            draw_order: Base draw order for layering. Defaults to 1.
        """
        super().__init__(name, container)

        self._entities: dict[str, TacticalEntity] = {}
        self._geofence_points: list[tuple[float, float]] = []
        self._show_grid = show_grid
        self._icon_size = icon_size
        self._entity_labels: dict[str, Label] = {}
        self._breach_entities: set[str] = set()
        self._title_label: Label | None = None

        # Calculate display metrics
        self._margin = 0.05  # 5% margin from edges
        self._draw_order = draw_order

        # Initialize background/border vertices
        border_v = self.vertice_border(container)
        self.add_vertex(
            "border",
            8,
            GL_LINES,
            G(self.m_draw + draw_order),
            ("v2f/static", self.vertice_strip(border_v)),
            ("c4B/static", C["GREY"] * 8),
        )

        # Initialize grid if enabled
        if show_grid:
            grid_v = self._compute_grid_vertices(divisions=4)
            self.add_vertex(
                "grid",
                len(grid_v) // 2,
                GL_LINES,
                G(self.m_draw + draw_order),
                ("v2f/static", grid_v),
                ("c4B/static", tuple(list(C["GREY"][:3]) + [64]) * (len(grid_v) // 2)),
            )

        # Placeholder for geofence (will be updated dynamically)
        self.add_vertex(
            "geofence",
            MAX_POLYGON_POINTS,
            GL_LINES,
            G(self.m_draw + draw_order + 1),
            ("v2f/dynamic", (0.0,) * (MAX_POLYGON_POINTS * 2)),
            ("c4B/dynamic", C["GREEN"] * MAX_POLYGON_POINTS),
        )

        # Placeholder for entity icons
        # We reserve space for MAX_ENTITIES * 8 vertices (4 points per diamond * 2 coords)
        max_icon_vertices = MAX_ENTITIES * 8
        self.add_vertex(
            "entities",
            max_icon_vertices,
            GL_LINES,
            G(self.m_draw + draw_order + 2),
            ("v2f/dynamic", (0.0,) * (max_icon_vertices * 2)),
            ("c4B/dynamic", C["CYAN"] * max_icon_vertices),
        )

        # Optional title label
        if title is not None:
            self._title_label = Label(
                title,
                x=container.x1 + 5,
                y=container.y2 - 15,
                font_name=self.font_name,
                font_size=F["SMALL"],
                color=C["WHITE"],
                group=G(self.m_draw + draw_order + 3),
            )
            self.vertex["title"] = self._title_label

    def _compute_grid_vertices(self, divisions: int = 4) -> list[float]:
        """Compute grid line vertices for the display background.

        Args:
            divisions: Number of grid divisions per axis. Defaults to 4.

        Returns:
            Flat list of vertex coordinates for GL_LINES.
        """
        vertices: list[float] = []
        c = self.container
        margin_x = c.w * self._margin
        margin_y = c.h * self._margin

        # Inner display area
        x_min = c.x1 + margin_x
        x_max = c.x2 - margin_x
        y_min = c.y1 + margin_y
        y_max = c.y2 - margin_y

        # Vertical lines
        for i in range(divisions + 1):
            x = x_min + (x_max - x_min) * (i / divisions)
            vertices.extend([x, y_min, x, y_max])

        # Horizontal lines
        for i in range(divisions + 1):
            y = y_min + (y_max - y_min) * (i / divisions)
            vertices.extend([x_min, y, x_max, y])

        return vertices

    def _norm_to_absolute(self, x_norm: float, y_norm: float) -> tuple[float, float]:
        """Convert normalized coordinates to absolute screen coordinates.

        Args:
            x_norm: Normalized X (0.0 to 1.0).
            y_norm: Normalized Y (0.0 to 1.0).

        Returns:
            Tuple of (absolute_x, absolute_y) screen coordinates.
        """
        c = self.container
        margin_x = c.w * self._margin
        margin_y = c.h * self._margin

        # Clamp normalized values to valid range
        x_norm = max(0.0, min(1.0, x_norm))
        y_norm = max(0.0, min(1.0, y_norm))

        x_abs = c.x1 + margin_x + (c.w - 2 * margin_x) * x_norm
        y_abs = c.y1 + margin_y + (c.h - 2 * margin_y) * y_norm

        return (x_abs, y_abs)

    def _get_icon_vertices(
        self, x: float, y: float, icon_type: str, size: float
    ) -> list[float]:
        """Generate vertices for an entity icon.

        Args:
            x: Absolute X center position.
            y: Absolute Y center position.
            icon_type: Shape type - 'diamond', 'circle', 'triangle', 'square'.
            size: Icon size in pixels.

        Returns:
            Flat list of vertex coordinates for GL_LINES.
        """
        half = size / 2

        if icon_type == "diamond":
            # Diamond shape (4 points)
            points = [
                (x, y + half),  # Top
                (x + half, y),  # Right
                (x, y - half),  # Bottom
                (x - half, y),  # Left
            ]
        elif icon_type == "square":
            # Square shape
            points = [
                (x - half, y + half),  # Top-left
                (x + half, y + half),  # Top-right
                (x + half, y - half),  # Bottom-right
                (x - half, y - half),  # Bottom-left
            ]
        elif icon_type == "triangle":
            # Triangle pointing up
            h = half * 1.15  # Adjust for visual balance
            points = [
                (x, y + h),  # Top
                (x + half, y - h * 0.5),  # Bottom-right
                (x - half, y - h * 0.5),  # Bottom-left
            ]
        elif icon_type == "circle":
            # Approximated circle (octagon for simplicity)
            points = []
            for i in range(8):
                angle = i * math.pi / 4
                px = x + half * math.cos(angle)
                py = y + half * math.sin(angle)
                points.append((px, py))
        else:
            # Default to diamond
            points = [
                (x, y + half),
                (x + half, y),
                (x, y - half),
                (x - half, y),
            ]

        # Convert closed polygon points to line segments
        vertices: list[float] = []
        for i, point in enumerate(points):
            next_point = points[(i + 1) % len(points)]
            vertices.extend([point[0], point[1], next_point[0], next_point[1]])

        return vertices

    def _get_status_color(self, status: str, breach: bool = False) -> tuple[int, ...]:
        """Get color for entity status.

        Args:
            status: Entity status string.
            breach: Whether entity is in breach state.

        Returns:
            RGBA color tuple.
        """
        if breach:
            return C["RED"]

        status_upper = status.upper()
        if status_upper in STATUS_COLORS:
            return STATUS_COLORS[status_upper]

        # Fallback mapping
        color_map = {
            "NORMAL": C["GREEN"],
            "WARNING": C["YELLOW"],
            "CRITICAL": C["RED"],
            "DISABLED": C["GREY"],
            "ACTIVE": C["CYAN"],
            "RESOLVED": C["GREEN"],
            "AUTO": C["CYAN"],
            "MANUAL": C["YELLOW"],
        }
        return color_map.get(status_upper, C["WHITE"])

    def set_geofence(self, points: list[tuple[float, float]] | None) -> None:
        """Set or clear the geofence polygon.

        Args:
            points: List of (x_norm, y_norm) tuples defining the polygon vertices,
                    or None to clear the geofence.
        """
        if points is None or len(points) < 3:
            self._geofence_points = []
            if self.is_visible() and "geofence" in self.on_batch:
                self.on_batch["geofence"].vertices = (0.0,) * (MAX_POLYGON_POINTS * 2)
            return

        # Limit polygon points to prevent unbounded memory
        if len(points) > MAX_POLYGON_POINTS // 2:
            points = points[: MAX_POLYGON_POINTS // 2]

        self._geofence_points = list(points)

        # Convert to absolute coordinates and create line segments
        vertices: list[float] = []
        for i, point in enumerate(points):
            x1, y1 = self._norm_to_absolute(point[0], point[1])
            next_point = points[(i + 1) % len(points)]
            x2, y2 = self._norm_to_absolute(next_point[0], next_point[1])
            vertices.extend([x1, y1, x2, y2])

        # Pad to fixed size
        while len(vertices) < MAX_POLYGON_POINTS * 2:
            vertices.append(0.0)

        if self.is_visible() and "geofence" in self.on_batch:
            self.on_batch["geofence"].vertices = vertices
            self.logger.record_state(self.name, "geofence_points", len(points))

    def get_geofence(self) -> list[tuple[float, float]]:
        """Get the current geofence polygon points.

        Returns:
            List of (x_norm, y_norm) tuples.
        """
        return list(self._geofence_points)

    def set_entity(self, entity: TacticalEntity) -> None:
        """Add or update an entity on the display.

        Args:
            entity: TacticalEntity to add or update.

        Raises:
            ValueError: If maximum entity count would be exceeded.
        """
        if entity.entity_id not in self._entities and len(self._entities) >= MAX_ENTITIES:
            raise ValueError(
                f"Maximum entity count ({MAX_ENTITIES}) exceeded. "
                f"Remove entities before adding new ones."
            )

        self._entities[entity.entity_id] = entity
        self._update_entity_display()

    def remove_entity(self, entity_id: str) -> None:
        """Remove an entity from the display.

        Args:
            entity_id: ID of entity to remove.
        """
        if entity_id in self._entities:
            del self._entities[entity_id]
            self._breach_entities.discard(entity_id)
            if entity_id in self._entity_labels:
                self._entity_labels[entity_id].delete()
                del self._entity_labels[entity_id]
            self._update_entity_display()

    def clear_entities(self) -> None:
        """Remove all entities from the display."""
        self._entities.clear()
        self._breach_entities.clear()
        for label in self._entity_labels.values():
            label.delete()
        self._entity_labels.clear()
        self._update_entity_display()

    def set_breach(self, entity_id: str, in_breach: bool) -> None:
        """Set or clear breach state for an entity.

        Args:
            entity_id: ID of the entity.
            in_breach: Whether entity is in breach state.
        """
        if in_breach:
            self._breach_entities.add(entity_id)
        else:
            self._breach_entities.discard(entity_id)
        self._update_entity_display()

    def get_entities(self) -> dict[str, TacticalEntity]:
        """Get all current entities.

        Returns:
            Dictionary of entity_id -> TacticalEntity.
        """
        return dict(self._entities)

    def _update_entity_display(self) -> None:
        """Refresh the entity vertex buffer with current entity states."""
        if not self.is_visible():
            return

        vertices: list[float] = []
        colors: list[int] = []
        icon_size = self.container.w * self._icon_size

        for entity_id, entity in self._entities.items():
            x, y = self._norm_to_absolute(entity.x_norm, entity.y_norm)
            icon_v = self._get_icon_vertices(x, y, entity.icon_type, icon_size)
            vertices.extend(icon_v)

            # Get color based on status and breach state
            in_breach = entity_id in self._breach_entities
            color = self._get_status_color(entity.status, in_breach)

            # Each icon vertex needs a color
            num_vertices = len(icon_v) // 2
            colors.extend(color * num_vertices)

        # Pad to fixed buffer size
        max_icon_vertices = MAX_ENTITIES * 8
        while len(vertices) < max_icon_vertices * 2:
            vertices.append(0.0)
        while len(colors) < max_icon_vertices * 4:
            colors.append(0)

        if "entities" in self.on_batch:
            self.on_batch["entities"].vertices = vertices
            self.on_batch["entities"].colors = colors

    def update_entity_position(
        self, entity_id: str, x_norm: float, y_norm: float
    ) -> None:
        """Update just the position of an existing entity.

        Args:
            entity_id: ID of entity to update.
            x_norm: New normalized X position.
            y_norm: New normalized Y position.
        """
        if entity_id not in self._entities:
            return

        old_entity = self._entities[entity_id]
        # Create new immutable entity with updated position
        new_entity = TacticalEntity(
            entity_id=old_entity.entity_id,
            x_norm=x_norm,
            y_norm=y_norm,
            icon_type=old_entity.icon_type,
            status=old_entity.status,
            label=old_entity.label,
            heading_deg=old_entity.heading_deg,
        )
        self._entities[entity_id] = new_entity
        self._update_entity_display()

    def set_geofence_color(self, color: tuple[int, ...]) -> None:
        """Set the geofence polygon color.

        Args:
            color: RGBA color tuple.
        """
        if self.is_visible() and "geofence" in self.on_batch:
            self.on_batch["geofence"].colors = color * MAX_POLYGON_POINTS

    def show(self) -> None:
        """Show the widget and update displays."""
        super().show()
        # Refresh geofence and entities after showing
        if self._geofence_points:
            self.set_geofence(self._geofence_points)
        self._update_entity_display()

    def hide(self) -> None:
        """Hide the widget."""
        super().hide()
        # Clear entity labels
        for label in self._entity_labels.values():
            label.batch = None

