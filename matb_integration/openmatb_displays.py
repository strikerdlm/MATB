"""Read native display ordering without creating an experiment window."""
from __future__ import annotations

import json


def connected_displays() -> list[dict]:
    import pyglet
    pyglet.options["shadow_window"] = False
    from pyglet.display import get_display

    return [{"index": index, "label": f"Display {index + 1}",
             "width": screen.width, "height": screen.height, "x": screen.x, "y": screen.y}
            for index, screen in enumerate(get_display().get_screens())]


if __name__ == "__main__":
    print(json.dumps(connected_displays()))
