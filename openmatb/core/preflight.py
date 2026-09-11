"""Observational initial response mapping; never starts a plugin or changes its parameters."""
from copy import deepcopy
import hashlib
import json
import re

TASKS = ('sysmon', 'track', 'resman', 'communications')


def snapshot(scheduler):
    enabled = sorted({e.plugin for e in scheduler.events if e.plugin in TASKS and e.command == ['start']})
    parameters = {key: deepcopy(scheduler.plugins[key].parameters) for key in enabled}
    issues = []
    for event in scheduler.events:
        if event.plugin not in parameters or len(event.command) != 2: continue
        address, value = event.command
        relevant = (address.startswith('keys-') or address.endswith('-key') or address in {'inverseaxis','joystickforce','owncallsign','callsignregex'})
        if not relevant: continue
        if event.time_sec != 0:
            issues.append('dynamic_response_mapping'); continue
        # A regex change generates a new callsign during plugin progression, so it cannot be predicted here.
        if address == 'callsignregex' and value != parameters[event.plugin].get(address):
            issues.append('unresolved_generated_callsign'); continue
        target = parameters[event.plugin]
        parts = address.split('-')
        for part in parts[:-1]: target = target[part]
        original = target.get(parts[-1])
        target[parts[-1]] = value.lower() == 'true' if isinstance(original, bool) else int(value) if isinstance(original, int) else value
    mapping = {}
    for task, values in parameters.items():
        if task == 'sysmon': mapping[task] = {group:{key:{'key':v['key']} for key,v in values[group].items()} for group in ['lights','scales']}
        elif task == 'communications': mapping[task] = dict(keys=values['keys'], owncallsign=values['owncallsign'])
        elif task == 'track': mapping[task] = {key:values[key] for key in ['inverseaxis','joystickforce']}
        elif task == 'resman': mapping[task] = {key:value['key'] for key,value in values['pump'].items()}
    requires_joystick = 'track' in enabled or 'JOY_' in json.dumps(mapping)
    joystick = scheduler.joystick
    controller = None
    if joystick and requires_joystick:
        device = joystick.device
        controller = dict(name=str(getattr(getattr(device, 'device', device), 'name', 'unknown')),
            buttons=len(device.buttons), axes=[axis for axis in ['x','y'] if isinstance(getattr(device,axis,None),(int,float))], selection='pyglet-first-device')
        if 'track' in enabled and controller['axes'] != ['x','y']: issues.append('required_controller_axes_unavailable')
        for button in re.findall(r'JOY_BTN_(\d+)', json.dumps(mapping)):
            if int(button) > controller['buttons']:
                issues.append('required_controller_button_unavailable')
        if 'JOY_HAT_' in json.dumps(mapping) and any(getattr(device,axis,None) is None for axis in ['hat_x','hat_y']):
            issues.append('required_controller_hat_unavailable')
    if 'communications' in mapping and not mapping['communications']['owncallsign']: issues.append('unresolved_generated_callsign')
    if requires_joystick and not controller: issues.append('required_controller_unavailable')
    value = dict(schema_version='native-preflight-v1', enabled_tasks=enabled, mapping=mapping, controller=controller, issues=sorted(set(issues)))
    value['sha256'] = hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return value
