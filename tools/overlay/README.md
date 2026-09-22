# Charybdis Overlay - Windows preview

A local desktop overlay for the Charybdis, showing the active layer stack and
held modifiers. Opacity, palette, size, position and hide delay are adjustable.
Set hide delay to 0 to keep it visible. A separate control window remains open;
minimise it while typing. Closing it exits the app. No startup service is installed.

## First setup

1. Keep your current firmware as a fallback. Flash only the left half with
   `charybdis-left-OVERLAY.uf2` from the companion firmware build. Do not use
   settings-reset or Restore Stock Settings: your Studio bindings should remain.
2. Download and extract the complete `Charybdis-Overlay-Windows` artifact ZIP.
   Keep the `_internal` directory beside `CharybdisOverlay.exe`.
3. Run `CharybdisOverlay.exe`. Connect the left half by USB. The app locates the
   extra serial interface automatically. It does not need Studio unlocking.
4. Use your layer and Shift keys. Adjust the appearance in the control window.
   Use X/Y controls to place the overlay; it defaults to click-through on Windows.
5. Edit in Studio as usual. The overlay picks up live keymap changes automatically,
   normally within about a second. Save your edits in Studio to persist them.

The extra serial interface is read-only and independent of Studio. It sends
keymap assignments, active layer IDs and modifier state whenever a client opens
it; it does not enforce Studio's unlock on these reads. It sends no ordinary key
presses and does not record typing. No cloud connection or account is required.

## What it shows

- Effective bindings resolved through active layers in firmware priority order.
- Held Shift, Ctrl, Alt and Super; Shift changes letter case and punctuation.
- US English symbol labels. Other OS layouts/AltGr mappings are not yet translated.
- Windows Caps Lock affects case; numeric keypad labels remain KP keys (Num Lock
  navigation is not translated). Custom behaviors show a name and raw parameters
  when the app cannot interpret them. Macro bodies are not expanded.
- Cached layout preview when disconnected. This is explicitly labelled offline;
  live state needs the optional firmware and USB. Bluetooth-only use is not supported.
- Automatic hiding after inactivity. With Keep visible while typing enabled, every
  Windows keyboard press (including repeats) restarts the timer and brings a hidden
  overlay back. This applies to all keyboards, only while Charybdis is connected.
  The listener keeps an activity flag only; it never reads or records key codes.
- Transparent background removes the rectangle behind the keys, while keeping
  key tiles and labels visible. Opacity still applies to the visible keys.

The firmware checks modifiers and layer state every 25 ms only while this serial
interface is open; it checks for keymap edits once a second. Transmission stops
when USB is suspended. This does not claim to fix the separate PC wake issue.
Very brief state changes shorter than a sample period may not appear.

## Source launch / development

With Python 3.12+ installed, run `Start-Overlay.cmd`; it creates a local virtual
environment and installs pyserial 3.5. Or install requirements.txt and run
`python overlay.py`. Tests: `python -m unittest -v test_overlay.py`.

Settings and the last layout are cached in `%LOCALAPPDATA%\CharybdisOverlay`.
Delete that directory to reset the app's preferences (not the keyboard).

## Physical acceptance checks

This first version needs testing on the actual keyboard and Windows desktop:
verify transparent-key resolution, both Shift keys, the automatic mouse layer,
Studio edits appearing without reconnecting, no focus stealing, hiding/opacity,
USB disconnect/reconnect, and PC sleep. The published build checks cannot prove
those device-specific behaviours. Stop the app and restore the earlier left UF2
if the new USB interface causes problems; preserve Studio settings.
