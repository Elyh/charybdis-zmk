# Charybdis trackball investigation — 19 September 2026

Baseline USB test: all six original variants compiled successfully in GitHub Actions.
Hardware result: synthetic 6/7/8/9 pointer movement works; the ball does not.
The 20-second serial capture contained only matrix startup messages.
See DIAG2 below for the next diagnostic; baseline build link below is historical.
Tested firmware commit: 41474924a9ad5ad41009e21cae516432c367b89b.
Verified build: https://github.com/Elyh/charybdis-zmk/actions/runs/35439718596
Download its `firmware` artifact; first flash only `charybdis-right-USB-TEST.uf2`.
Later documentation-only commits do not change these firmware binaries.
Baseline: Elyh/charybdis-zmk commit 3d78a026757e05e56a39781968860f15844ee0fb.
Branch: troubleshoot/trackball-usb-isolation.

## Confirmed findings

The right .conf commented out CONFIG_ZMK_SPLIT=y, but both Kconfig.shield and
Kconfig.defconfig still defaulted split mode to y. A comment is not an override.
The attempted local input listener therefore did not make this a standalone mouse:
ZMK compiles its listener only on a central or a non-split device, and USB HID has
the same role restriction. This invalidates the right-USB isolation test; it does
not by itself establish why the normal split trackball was stationary.

The normal split routing is structurally present: right sensor -> input-split 0 ->
left input-split 0 -> left listener. Both halves enable pointing. Matrix mapping
has 56 unique positions and 56 key bindings. No sensor pin overlaps the matrix
pins after resolving the nice!nano connector mapping.

The driver checks observation self-test bits and product ID 0x3e before printing
PMW3610 initialized. That is evidence of successful initial sensor communication,
not proof of optical tracking, IRQ operation, or host reports. It then enables the
motion interrupt; an interrupt configuration failure can occur after that message.
Debug x/y messages are emitted when the driver's motion-read routine runs.

## Wiring baseline recovered from latest conversation

| Signal | MCU pin |
| --- | --- |
| CS | P0.20 |
| Shared SDIO (MOSI and MISO in pinctrl) | P0.17 |
| SCLK | P0.08 |
| MOTION (carrier pad labelled MISO) | P0.06 |

The latest conversation says factory wiring was restored. This table matches the
current overlay and the driver's shared-SDIO example. Older P1.01/P1.02/P1.07
suggestions are superseded. No rewiring is requested for this test.

## Changes

- Keep ordinary right firmware explicitly split; remove the misleading local listener.
- Remove duplicate defaults from Kconfig.shield; retain them in Kconfig.defconfig.
- Add a separate USB test snippet: split off, BLE off, USB on, direct sensor listener,
  split input node disabled, driver debug on, report throttling off for isolation.
- USB test only: right 6/7/8/9 keys move left/right/up/down while held, independently
  of the sensor. Remaining key mapping is unchanged.
- Add explicit normal, USB-test, and split-log artifact names. Logging variants
  use ZMK's USB logging snippet so a serial console is actually configured.
- Select board revision 2.0.0 explicitly (the existing default).
- Pin ZMK, the reusable workflow, and the sensor driver to the audited commits.
  The previous build logs subsequently confirmed these are the same ZMK and
  sensor-driver revisions it used. Imported dependencies and build container remain
  upstream-managed, so this is not a fully frozen toolchain.

## Build and verify BEFORE flashing

Push this branch to the existing repository. Its workflow builds six artifacts.
No new repository is necessary. Check that the run is for the new branch/commit.
If it fails, supply the failed job log; do not flash an artifact from an older run.

In the USB-TEST job's printed Kconfig check:

- CONFIG_ZMK_USB=y and CONFIG_ZMK_INPUT_LISTENER=y.
- CONFIG_ZMK_POINTING=y and CONFIG_PMW3610_ALT=y.
- CONFIG_ZMK_USB_LOGGING=y and CONFIG_PMW3610_ALT_LOG_LEVEL_DBG=y.
- No enabled CONFIG_ZMK_SPLIT, CONFIG_ZMK_BLE, or CONFIG_ZMK_INPUT_SPLIT.

In that job's printed devicetree check that trackball_listener targets trackball,
trackball_split is disabled, and CS/IRQ/pinctrl match the table above.
The normal right build must still have split/input-split enabled and central off.
The normal left build must have central and its input listener enabled.

## First physical test — right half only

1. Leave the wiring as restored. Turn the left half off.
2. Put the right controller into its UF2 bootloader using the reset method that
   already works for your controller. Copy charybdis-right-USB-TEST.uf2 onto it.
3. Connect the right half directly to the PC using a known data USB cable. This
   test uses USB only; Bluetooth pairing is unnecessary. Do not use settings-reset.
4. Hold the physical 6, 7, 8, and 9 keys in turn. They should move the cursor
   left, right, up, and down. Release each before trying the next.
5. Open the new USB serial port at 115200 baud with DTR enabled. Capture output
   while moving the ball for about ten seconds. If initialization is missed,
   reconnect the serial console promptly after a normal reset (not bootloader).
6. Return whether keyboard keys work, whether synthetic pointer movement works,
   whether ball movement works, and the full captured log. Record the build SHA.

| Observation | Next investigation |
| --- | --- |
| Synthetic movement fails too | Verify flashed artifact, resolved config, USB enumeration and HID output before touching sensor wiring. |
| Synthetic works; initialization fails | Use exact self-test/product-ID/SPI error to investigate sensor communication or power. |
| Synthetic works; init succeeds; no x/y lines | Check for interrupt errors; then investigate MOTION/optics. Absence of lines alone does not prove a broken wire. |
| x/y repeatedly zero while ball moves | Investigate optical geometry/surface and burst data; initialization alone does not prove tracking. |
| Nonzero x/y but no ball cursor movement | Investigate sensor input-event/listener/report path. |
| Ball works in USB test | Restore split builds and investigate forwarding/left host endpoint. |

Do not change wires or take live-board probe measurements until the log tells us
which check is necessary. Hardware tests cannot be performed from this workspace.

## Restore and test split operation

Flash charybdis-right-split.uf2 on the right and charybdis-left-split.uf2 on the
left. Turn both on and first test with the left connected to the PC over USB.
Normal right firmware is a peripheral; its USB connection is not the host mouse
connection. Use the matching -LOG builds if forwarding needs investigation.
Only investigate host BLE pairing/descriptor caching after left-USB works.
Do not reset existing bonds as the first step.

## Verification performed here and limits

Read the actual repository, audited ZMK Kconfig/listener/split implementations,
PMW3610 init/report code, nice!nano GPIO mapping, and Zephyr snippet support and
extra-overlay precedence. Parsed YAML; checked snippet paths, matrix uniqueness,
binding counts, sensor/matrix pin separation, and git whitespace errors.

GitHub Actions run 35439718596 completed successfully for all six variants.
The generated USB-test configuration was checked: USB, pointing, input listener,
PMW3610 and USB/debug logging are enabled; split, BLE and input-split are not.
The generated devicetree confirms a direct sensor listener, disabled split input,
restored pins, and four synthetic pointer bindings. The USB-test UF2 is 177152
bytes according to its build log. Normal left/right configurations preserve their
central/peripheral roles; the right logging variant enables sensor debug output.

The prior build 35435098920 also confirms the diagnosis: right split was enabled,
USB HID was disabled by dependencies, and the requested sensor debug option did
not take effect because logging was not enabled. The earlier initialization logs
must therefore be associated with their own diagnostic build, not assumed to come
from this latest default build.

Nonfatal upstream warnings remain for deprecated KSCAN, USB HID being unavailable
on ordinary split peripherals, and the USB-only test's unused settings backend.
None prevented compilation. No claim of hardware repair is made until the test
above is completed. GitHub access is now connected and the diagnostic branch is
published in draft PR https://github.com/Elyh/charybdis-zmk/pull/1 .

## Source references

- https://github.com/Elyh/charybdis-zmk/tree/3d78a026757e05e56a39781968860f15844ee0fb
- https://github.com/zmkfirmware/zmk/blob/9ebbeff0a8b69a42f14aec022cdf16c7a107b9e0/app/src/pointing/Kconfig
- https://github.com/zmkfirmware/zmk/blob/9ebbeff0a8b69a42f14aec022cdf16c7a107b9e0/app/Kconfig
- https://github.com/badjeff/zmk-pmw3610-driver/blob/e970029b42f33613ca8f05baf311dc733cd5a390/src/pmw3610.c

## DIAG2: persistent status and scheduled sensor reads

Use the successful build for the commit that adds `src/sensor_probe.c`, and flash
only `charybdis-right-USB-DIAG2.uf2` on the right half. Left stays off; wiring stays
unchanged. The original USB test remains available for comparison.

Run the same 20-second PowerShell capture and move the ball throughout. DIAG2 waits
for serial DTR and repeats two status lines each second. For the first 10 seconds
it observes normal IRQ operation. It then supplements IRQ handling by submitting
the existing driver's own motion-read work every ~20 ms while the serial port is
open. This is an isolation test, not a recommended permanent polling fix.

It suppresses ordinary log traffic and sends its own `printk` status directly to
the USB console, avoiding the deferred log queue. A dedicated reporting thread
can continue even if the system workqueue stops. All sensor state snapshots and
read-only product-ID transactions run on the driver's system workqueue. The driver
itself, sensor wiring, SPI rate, and initialization sequence are unchanged.

Status interpretation:

- `device=1` means the Zephyr device initialized; `ready=1 step=4` separately means
  the driver's asynchronous sensor initialization completed.
- `init_err` is the driver's initialization error, not a general motion-read error.
- `id_rc=0 id=0x3e` is a successful expected product-ID read. `id_rc=-999` means no
  completed diagnostic ID sample yet, not a sensor error code.
- `work` should increase; a fixed value with repeating lines indicates workqueue
  progress needs investigation. It is not proof of a hardware failure.
- `motion_raw=0` samples the active-low MOTION pin asserted; `1` samples it high.
  Individual samples can miss pulses. `irq` is a cumulative callback count, and
  `irq_monitor=0` means the monitor callback was installed successfully.
- `polls` counts accepted work submissions, not guaranteed completed SPI reads.
  `submit` records the latest submission result; coalesced requests are possible.
- `events` counts input events from the physical trackball device only. Synthetic
  movement keys do not increase it. `last_xy` stores last reported axis values,
  not current velocity, so it may retain nonzero values after movement stops.
- Motion appearing only during POLL is evidence to investigate IRQ signalling or
  servicing. No events in either mode does not alone prove optical failure.

The diagnostic uses private driver structs from the pinned upstream revision.
Re-audit this adapter before changing the driver version. It is compiled only
when CONFIG_CHARYBDIS_SENSOR_PROBE=y, restricted to the standalone USB diagnostic;
normal left/right and original USB-test firmware do not include this code.
