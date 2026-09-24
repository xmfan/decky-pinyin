"""Read-only Steam Deck L4 input; no controller remapping or input grab.

HID layout follows Decky-Translator's HidrawButtonMonitor (GPL-3.0) and
Linux hid-steam: report type 9, ButtonsH bit 9 at bytes 12..15.
"""
import asyncio
import os
from pathlib import Path


def l4_pressed(packet):
    if len(packet) < 16 or packet[:3] != b"\x01\x00\x09":
        return None
    return bool(int.from_bytes(packet[12:16], "little") & 0x200)


class L4Gesture:
    def __init__(self, callback, hold_seconds=.65):
        self.callback = callback
        self.hold_seconds = hold_seconds
        self.down = False
        self.held = False
        self.timer = None
        self.armed = False

    def update(self, pressed):
        # Enabling while L4 is held must not activate anything on its release.
        if not self.armed:
            self.armed = not pressed
            return
        if pressed == self.down:
            return
        self.down = pressed
        if pressed:
            self.held = False
            self.timer = asyncio.get_running_loop().call_later(self.hold_seconds, self._hold)
        else:
            if self.timer:
                self.timer.cancel()
                self.timer = None
            if not self.held:
                self.callback("capture")

    def _hold(self):
        self.timer = None
        if self.down:
            self.held = True
            self.callback("dismiss")

    def close(self):
        if self.timer:
            self.timer.cancel()
        self.timer = None
        self.down = self.held = self.armed = False


class L4Monitor:
    def __init__(self, callback, on_error):
        self.gesture = L4Gesture(callback)
        self.on_error = on_error
        self.fd = None
        self.loop = None

    def start(self):
        self.loop = asyncio.get_running_loop()
        candidates = []
        for device in Path("/sys/class/hidraw").glob("hidraw*"):
            try:
                fields = dict(line.split("=", 1) for line in (device / "device/uevent").read_text().splitlines() if "=" in line)
                _, vendor, product = fields.get("HID_ID", "::").split(":")
                if int(vendor, 16) == 0x28DE and int(product, 16) == 0x1205:
                    candidates.append(device)
            except (OSError, ValueError):
                continue
        candidates.sort(key=lambda p: ":1.2/" not in str(p.resolve()))
        errors = []
        for device in candidates:
            try:
                fd = os.open("/dev/" + device.name, os.O_RDONLY | os.O_NONBLOCK)
                self.fd = fd
                self.loop.add_reader(fd, self._read)
                return "L4 ready · tap to capture, hold to dismiss"
            except OSError as exc:
                errors.append(str(exc))
                if self.fd is not None:
                    os.close(self.fd)
                    self.fd = None
        return "L4 unavailable; use Capture now. " + (errors[-1] if errors else "Steam Deck controller not found.")

    def _read(self):
        try:
            for _ in range(64):
                packet = os.read(self.fd, 64)
                if not packet:
                    raise OSError("Controller disconnected")
                pressed = l4_pressed(packet)
                if pressed is not None:
                    self.gesture.update(pressed)
        except BlockingIOError:
            pass
        except OSError as exc:
            self.close()
            self.on_error(f"L4 disconnected; disable and enable to reconnect. {exc}")

    def close(self):
        self.gesture.close()
        if self.fd is not None:
            self.loop.remove_reader(self.fd)
            os.close(self.fd)
            self.fd = None
