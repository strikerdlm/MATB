# Copyright 2025, by OpenMATB contributors.
# License : CeCILL, version 2.1 (see the LICENSE file)

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from core import validation
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import Simpletext
from plugins.abstractplugin import AbstractPlugin


@dataclass
class WeaponStock:
    """Represents the remaining inventory for a single weapon type."""

    name: str
    capacity: int
    remaining: int

    def expend(self, count: int) -> int:
        actual = min(self.remaining, count)
        self.remaining -= actual
        return actual

    def reload(self, count: int) -> None:
        self.remaining = min(self.capacity, self.remaining + count)

    def reset(self, capacity: int) -> None:
        self.capacity = capacity
        self.remaining = capacity

    def as_display(self) -> str:
        return f'{self.name} | {self.remaining}/{self.capacity}'


class Weaponsinventory(AbstractPlugin):
    """Tracks weapons loadouts and expended rounds."""

    def __init__(self, label: str = '', taskplacement: str = 'topright', taskupdatetime: int = 500) -> None:
        super().__init__(label or _('Weapons Inventory'), taskplacement, taskupdatetime)

        self.validation_dict = {
            'lowwarnratio': validation.is_positive_float,
        }
        self.parameters.update({
            'lowwarnratio': 0.25,
        })

        self.stocks: Dict[str, WeaponStock] = {}
        self._widget: Optional[Simpletext] = None

        self.parameters['taskfeedback']['overdue'].update({
            'active': True,
            'color': C['ORANGE'],
            'delayms': 0,
            'blinkdurationms': 400,
        })

    def start(self) -> None:
        self.stocks.clear()
        super().start()

    def create_widgets(self) -> None:
        super().create_widgets()
        header = _('Weapon | Remaining')
        self.add_widget(
            'header',
            Simpletext,
            container=self.task_container,
            text=header,
            font_size=F['SMALL'],
            y=0.9,
            color=C['WHITE'],
            bold=True,
        )
        self._widget = self.add_widget(
            'inventory',
            Simpletext,
            container=self.task_container,
            text=_('No weapons loaded.'),
            font_size=F['SMALL'],
            y=0.6,
            wrap_width=0.95,
            color=C['WHITE'],
        )

    def refresh_widgets(self) -> bool:
        if not super().refresh_widgets():
            return False
        self._update_widget()
        self._update_overdue()
        return True

    # Scenario commands -------------------------------------------------
    def load(self, payload: str) -> None:
        parts = self._split(payload, 2)
        if not parts:
            return
        name = parts[0].strip().upper()
        try:
            count = int(float(parts[1]))
        except (TypeError, ValueError):
            return
        count = max(0, count)
        stock = self.stocks.get(name)
        if stock is None:
            stock = WeaponStock(name=name, capacity=count, remaining=count)
            self.stocks[name] = stock
        else:
            stock.reset(count)
        self.log_performance('weapon_load', f'{name}:{count}')

    def expend(self, payload: str) -> None:
        parts = self._split(payload, 1)
        if not parts:
            return
        name = parts[0].strip().upper()
        count = 1
        if len(parts) > 1:
            try:
                count = int(float(parts[1]))
            except (TypeError, ValueError):
                return
        count = max(1, count)
        stock = self.stocks.get(name)
        if stock is None:
            return
        spent = stock.expend(count)
        if spent <= 0:
            return
        self.log_performance('weapon_expended', f'{name}:{spent}:{stock.remaining}')
        if stock.remaining == 0:
            self.log_performance('weapon_empty', name)

    def reload(self, payload: str) -> None:
        parts = self._split(payload, 1)
        if not parts:
            return
        name = parts[0].strip().upper()
        stock = self.stocks.get(name)
        if stock is None:
            return
        if len(parts) > 1:
            try:
                added = int(float(parts[1]))
            except (TypeError, ValueError):
                return
        else:
            added = stock.capacity - stock.remaining
        if added <= 0:
            return
        stock.reload(added)
        self.log_performance('weapon_reload', f'{name}:{added}:{stock.remaining}')

    # Helpers -----------------------------------------------------------
    def _split(self, payload: str, min_parts: int) -> Optional[list[str]]:
        if not payload:
            return None
        parts = [part.strip() for part in payload.split(',') if part.strip()]
        if len(parts) < min_parts:
            return None
        return parts

    def _update_widget(self) -> None:
        if self._widget is None:
            return
        if not self.stocks:
            self._widget.set_text(_('No weapons loaded.'))
            return
        ordered = sorted(self.stocks.values(), key=lambda stock: stock.name)
        self._widget.set_text('\n'.join(stock.as_display() for stock in ordered))

    def _update_overdue(self) -> None:
        overdue = self.parameters['taskfeedback']['overdue']
        ratio = float(self.parameters['lowwarnratio'])
        overdue['active'] = True
        overdue['_is_visible'] = any(
            stock.capacity > 0 and (stock.remaining / stock.capacity) <= ratio
            for stock in self.stocks.values()
        )


