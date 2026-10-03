# Polar H10 connection and handover

The main action is **Buscar y conectar H10**. An eight-second scan connects one
available candidate automatically; multiple visible candidates always require
an explicit choice, including when only one is currently connectable. Discovery
alone never prepares or starts a recording. The redundant broadcast-listening
action is removed from the acquisition page; the API remains compatible.

**Cambiar de banda** releases the previous idle connection and starts fresh
discovery. After a finished standalone capture it also clears the participant
selection and retains the previous review/downloads under **Última captura
guardada** for this page session. Assigned study identity remains fixed; move to
the next participant's assignment through the visit. Prepared or active captures
lock device changes. A failed disconnect retains the selected capture.

Scan aliases stay attached to the same native device during this transport's
lifetime, independent of advertisement order. They are not permanent device IDs;
physical identity checks are still necessary after a service restart. Addresses
remain private inside the transport and are never added to API views or files.

Connection status refreshes with capture status. An unexpected idle disconnect
is visible immediately to the backend, and a subsequent scan releases the dead
client. During capture, disconnection still records a gap and blocks scan/connect
until finalization. Connection plus capability negotiation has a 30-second
timeout, with a specific retry message; unsuccessful attempts require fresh
discovery tokens. Bluetooth-disabled, occupied, expired-token, empty-scan and
connection-failure states provide actionable text.

Verification (2026-10-03):

- 22 focused Python tests: transport scan ordering/privacy, runtime disconnect
  and timeout recovery, active-capture exclusion, capture API and standalone flow.
- 19 frontend tests: restoration, participant selection, single/multiple device
  flows, empty scans, fresh-token retries, failed handover and active-record locks.
- TypeScript and focused ESLint passed.
- Playwright CLI synthetic browser flow: choose the second of two devices,
  prepare/start/stop, switch to a single new device, verify empty participant
  selection and retained previous review. No page/console errors.
- Adjacent screenshot contains only synthetic state, no physiological samples.

No live H10-to-H10 handover was verified in this change. These checks establish
software behavior, not radio reliability or correct physical participant matching.
The connection help follows Polar's advice to wet and fit the strap and check
other receivers: [official H9/H10 troubleshooting](https://support.polar.com/en/troubleshooting-polar-h9-h10-heart-rate-sensor).
