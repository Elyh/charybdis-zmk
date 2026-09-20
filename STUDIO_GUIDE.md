# Charybdis daily-use firmware and ZMK Studio

This builds on the user-confirmed working sensor orientation from commit
`e37e9cf31e13bc12617a5bde0c03e55634c61529`. Sensor wiring and orientation maths are unchanged.

## Flash and connect

1. Keep the previous working firmware ZIP as a fallback.
2. Flash `charybdis-left-split.uf2` to the left controller and
   `charybdis-right-split.uf2` to the right controller. Do not flash the diagnostic
   or settings-reset files for normal use.
3. Connect the left half by USB. Open https://zmk.studio/ in Edge or Chrome,
   or install the native Studio app. Firefox does not support this web connection.
4. Hold the left thumb key that normally types Tab (about 200 ms), then hold Esc.
   While holding both, tap V to select USB output.
5. Connect to the keyboard in Studio. Use the same two held keys and tap U to
   unlock editing. Release the keys, edit bindings, and save in Studio.

The visual layout is a flattened approximation of the curved shell; all 56
positions follow the existing matrix order. Verify thumb positions using their
old typing functions below, then adjust their bindings in Studio to taste.

## Typing and navigation

The number row is restored. Both normal Shift keys remain unchanged.
The left thumb Tab key still types Tab when tapped; hold it to access Navigation.
It is physical R5C6 / key position 50 in the current transform.

On Navigation:
- 1–0 = F1–F10; Delete = F11; backslash = F12.
- I/J/K/L = Up/Left/Down/Right.
- U/O = Home/End; P/semicolon = Page Up/Page Down.
- R/T = left/right square bracket; F/G = minus/equals.
- N/M/comma = previous track/play-pause/next track.
- period/slash/right Shift = volume down/up/mute.
- Hold Esc as well to access Settings.

On Settings:
- 1–5 select Bluetooth profiles 1–5 (internally numbered 0–4).
- V selects USB output; N selects Bluetooth; T toggles output.
- U unlocks ZMK Studio.
- Delete clears pairing for the selected Bluetooth profile only.
- There is no clear-all pairing shortcut.

## Left-thumb mouse controls

Moving the ball activates Mouse after a 250 ms typing-idle guard. It returns to
Typing after 1.5 seconds without movement, or when a non-excluded key is pressed.
Main Ctrl and Shift positions are excluded so modifier-clicks remain available.
Normal typing keys are transparent on Mouse.

| Physical left thumb | Position | Old typing function | Mouse function |
| --- | --- | --- | --- |
| Upper arc R5C4 | 48 | Left Alt | Left click / hold to drag |
| Upper arc R5C5 | 49 | Space | Right click |
| Upper arc R5C6 | 50 | Tab | Middle click |
| Lower arc R5C2 | 51 | Left Ctrl | Hold to scroll with the ball |
| Lower arc R5C3 | 52 | Left GUI/Super | Hold for quarter-speed precision |

These are the bindings in the last firmware, not early wiring-test outputs.
Right-thumb keys remain Enter, Backspace and Right Alt.
Scroll and Precision retain the same mouse buttons even if Mouse times out.
Vertical scrolling follows the corrected ball direction (towards you scrolls down);
horizontal scrolling is supported. Scroll gain starts at one step per 12 counts.
If both scroll and precision are held, scrolling takes priority.
After using the ball, wait 1.5 seconds before holding thumb Tab for Navigation,
or press a normal letter first to exit Mouse.

## Editing in Studio

Layers 0–5 are Typing, Mouse, Scroll, Precision, Navigation, Settings. Two spare
layers are compiled for future use. Scroll and Precision repeat Mouse bindings,
so update all three if rearranging mouse buttons. Keep the Navigation access key,
Settings access key, and Studio Unlock binding reachable.

The input processors refer to layer IDs 1–5: retain their roles. Studio edits key
assignments; rotation, auto-layer timing, scroll gain, and precision gain are
firmware settings. New Studio saves override future source keymap changes until
Studio's Restore Stock Settings is used. Record custom bindings before restoring.

## Physical checks after flashing

Confirm typing and number keys, the Studio connection/unlock, all three clicks,
click-and-drag with a pause longer than 1.5 seconds, scrolling, precision, normal
pointer direction, and both halves over Bluetooth. Runtime feel and actual USB
connection need testing on the physical keyboard; a CI build cannot prove them.
