"""Steam Deck HID monitor copied from Decky-Translator (GPL-3.0).

Upstream: cat-in-a-box/Decky-Translator @ 4358712ac2f0fb211462a573f554396d572e2095
See THIRD_PARTY.md and docs/UPSTREAM_PORT.md for attribution and local changes.
"""
import fcntl
import logging
import os
import queue
import select
import struct
import threading
import time

logger = logging.getLogger(__name__)

class HidrawButtonMonitor:
    """
    Monitors Steam Deck controller via /dev/hidraw for low-level button detection.
    Detects L4, L5, R4, R5, Steam, and QAM buttons that Steam normally intercepts.
    """

    # Device identification
    VALVE_VID = 0x28DE
    STEAMDECK_PID = 0x1205
    # InputPlumber virtual controller (used on non-Steam Deck handhelds like Legion Go)
    INPUTPLUMBER_PID = 0x12FB
    PACKET_SIZE = 64
    POLL_INTERVAL = 0.004  # 250Hz - matches controller report rate

    # HID ioctl command
    HIDIOCSFEATURE = lambda self, size: (0xC0000000 | (size << 16) | (ord('H') << 8) | 0x06)

    # HID commands for controller initialization
    ID_CLEAR_DIGITAL_MAPPINGS = 0x81
    ID_SET_SETTINGS_VALUES = 0x87
    SETTING_LEFT_TRACKPAD_MODE = 0x07
    SETTING_RIGHT_TRACKPAD_MODE = 0x08
    TRACKPAD_NONE = 0x07
    SETTING_STEAM_WATCHDOG_ENABLE = 0x2D

    # Button masks - ButtonsL (bytes 8-11, uint32 LE)
    BUTTONS_L = {
        'R2': 0x00000001,
        'L2': 0x00000002,
        'R1': 0x00000004,
        'L1': 0x00000008,
        'Y': 0x00000010,
        'B': 0x00000020,
        'X': 0x00000040,
        'A': 0x00000080,
        'DPAD_UP': 0x00000100,
        'DPAD_RIGHT': 0x00000200,
        'DPAD_LEFT': 0x00000400,
        'DPAD_DOWN': 0x00000800,
        'SELECT': 0x00001000,
        'STEAM': 0x00002000,
        'START': 0x00004000,
        'L5': 0x00008000,
        'R5': 0x00010000,
        'LEFT_PAD_TOUCH': 0x00080000,
        'RIGHT_PAD_TOUCH': 0x00100000,
        'L3': 0x00400000,
        'R3': 0x04000000,
    }

    # Button masks - ButtonsH (bytes 12-15, uint32 LE)
    BUTTONS_H = {
        'L4': 0x00000200,
        'R4': 0x00000400,
        'QAM': 0x00040000,
    }

    def __init__(self):
        self.device_fd = None
        self.device_path = None
        self.device_pid = None  # Track which product we connected to
        self.running = False
        self.thread = None
        self.event_queue = queue.Queue(maxsize=100)
        self.current_buttons = set()
        self.last_buttons_l = 0
        self.last_buttons_h = 0
        self.error_count = 0
        self.initialized = False
        self.lock = threading.Lock()
        logger.debug("HidrawButtonMonitor initialized")

    def find_device(self):
        """Find a Valve-compatible controller hidraw device.

        Supports:
        - Steam Deck controller (VID:28DE, PID:1205) with 3 hidraw interfaces
        - InputPlumber virtual controller (VID:28DE, PID:12FB) on non-Steam Deck handhelds

        For Steam Deck, we need interface :1.2 for gamepad data.
        For InputPlumber, there's typically a single virtual hidraw device.
        """
        steamdeck_candidates = []
        other_valve_candidates = []

        for i in range(10):
            path = f'/dev/hidraw{i}'
            if os.path.exists(path):
                uevent_path = f'/sys/class/hidraw/hidraw{i}/device/uevent'
                try:
                    with open(uevent_path, 'r') as f:
                        content = f.read().upper()
                        if '28DE' not in content:
                            continue
                        if '1205' in content:
                            steamdeck_candidates.append((i, path))
                            logger.debug(f"Found Steam Deck controller candidate at {path}")
                        elif '12FB' in content:
                            other_valve_candidates.append((i, path))
                            logger.debug(f"Found InputPlumber virtual controller candidate at {path}")
                        else:
                            # Valve devices use non-standard HID protocols - let evdev handle them
                            logger.debug(f"Skipping unsupported Valve hidraw at {path}")
                except Exception as e:
                    logger.debug(f"Cannot read uevent for hidraw{i}: {e}")

        # Prefer real Steam Deck controller (interface :1.2)
        if steamdeck_candidates:
            for i, path in steamdeck_candidates:
                try:
                    link_target = os.readlink(f'/sys/class/hidraw/hidraw{i}')
                    if ':1.2/' in link_target:
                        logger.info(f"Found Steam Deck gamepad interface at {path} (interface 1.2)")
                        self.device_pid = self.STEAMDECK_PID
                        return path
                except Exception as e:
                    logger.debug(f"Cannot read symlink for hidraw{i}: {e}")

            # Fallback: try data availability
            for i, path in steamdeck_candidates:
                try:
                    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                    try:
                        readable, _, _ = select.select([fd], [], [], 0.1)
                        if readable:
                            os.read(fd, 64)
                            os.close(fd)
                            logger.info(f"Found Steam Deck controller at {path} (has data)")
                            self.device_pid = self.STEAMDECK_PID
                            return path
                        os.close(fd)
                    except Exception:
                        os.close(fd)
                except Exception as e:
                    logger.debug(f"Cannot open {path}: {e}")

            # Last resort for Steam Deck
            path = steamdeck_candidates[-1][1]
            logger.info(f"Using Steam Deck controller at {path} (last candidate)")
            self.device_pid = self.STEAMDECK_PID
            return path

        # Try InputPlumber / other Valve virtual devices
        if other_valve_candidates:
            for i, path in other_valve_candidates:
                try:
                    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                    try:
                        readable, _, _ = select.select([fd], [], [], 0.1)
                        if readable:
                            os.read(fd, 64)
                            os.close(fd)
                            logger.info(f"Found Valve-compatible controller at {path} (has data)")
                            self.device_pid = self.INPUTPLUMBER_PID
                            return path
                        os.close(fd)
                    except Exception:
                        os.close(fd)
                except Exception as e:
                    logger.debug(f"Cannot open {path}: {e}")

            # Last resort
            path = other_valve_candidates[-1][1]
            logger.info(f"Using Valve-compatible controller at {path} (last candidate)")
            self.device_pid = self.INPUTPLUMBER_PID
            return path

        logger.info("No supported Valve hidraw device found; relying on evdev only")
        return None

    def send_feature_report(self, data):
        """Send a HID feature report to the device."""
        if self.device_fd is None:
            return False
        try:
            # Pad to 64 bytes
            buf = bytes(data) + bytes(64 - len(data))
            fcntl.ioctl(self.device_fd, self.HIDIOCSFEATURE(64), buf)
            return True
        except Exception as e:
            logger.error(f"Failed to send feature report: {e}")
            return False

    def initialize_device(self):
        """Open device and send initialization commands if needed."""
        if self.device_path is None:
            self.device_path = self.find_device()
            if self.device_path is None:
                return False

        try:
            # Open device with read/write access
            self.device_fd = os.open(self.device_path, os.O_RDWR)
            logger.info(f"Opened {self.device_path} for hidraw monitoring (pid={hex(self.device_pid or 0)})")

            # Only send init commands for real Steam Deck hardware
            if self.device_pid == self.STEAMDECK_PID:
                # Command 1: Clear digital mappings (disable lizard mode)
                if not self.send_feature_report([self.ID_CLEAR_DIGITAL_MAPPINGS]):
                    logger.warning("Failed to send CLEAR_DIGITAL_MAPPINGS")

                # Command 2: Set settings to disable trackpad emulation
                settings_cmd = [
                    self.ID_SET_SETTINGS_VALUES,
                    3,  # Number of settings
                    self.SETTING_LEFT_TRACKPAD_MODE, self.TRACKPAD_NONE,
                    self.SETTING_RIGHT_TRACKPAD_MODE, self.TRACKPAD_NONE,
                    self.SETTING_STEAM_WATCHDOG_ENABLE, 0,
                ]
                if not self.send_feature_report(settings_cmd):
                    logger.warning("Failed to send SET_SETTINGS_VALUES")

                logger.info("Steam Deck controller initialized for full button access")
            else:
                logger.info(f"Virtual/non-Steam Deck controller opened (skipping init commands)")

            self.initialized = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize hidraw device: {e}")
            if self.device_fd is not None:
                try:
                    os.close(self.device_fd)
                except:
                    pass
                self.device_fd = None
            return False

    def start(self):
        """Start the background monitoring thread."""
        if self.running:
            logger.warning("HidrawButtonMonitor already running")
            return True

        if not self.initialize_device():
            logger.error("Failed to initialize device, cannot start monitor")
            return False

        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info("HidrawButtonMonitor started")
        return True

    def stop(self):
        self.running = False

        if self.thread is not None:
            self.thread.join(timeout=2.0)
            self.thread = None

        if self.device_fd is not None:
            try:
                os.close(self.device_fd)
            except:
                pass
            self.device_fd = None

        self.initialized = False
        logger.info("HidrawButtonMonitor stopped")

    def _monitor_loop(self):
        """Background thread main loop - reads HID packets and generates events."""
        logger.info("HidrawButtonMonitor loop started")
        reconnect_delay = 2.0
        max_errors = 10

        while self.running:
            try:
                # Check if we need to reconnect
                if not self.initialized or self.device_fd is None:
                    logger.info("Attempting to reconnect to hidraw device")
                    if not self.initialize_device():
                        time.sleep(reconnect_delay)
                        continue

                # Wait for data with select (timeout to allow checking running flag)
                r, _, _ = select.select([self.device_fd], [], [], 0.1)
                if not r:
                    continue

                # Read packet
                data = os.read(self.device_fd, self.PACKET_SIZE)
                if len(data) >= 16:
                    self._process_packet(data)
                    self.error_count = 0

            except OSError as e:
                self.error_count += 1
                logger.warning(f"Hidraw read error ({self.error_count}): {e}")

                if self.error_count >= max_errors:
                    logger.error("Too many errors, closing device for reconnection")
                    self._close_device()
                    time.sleep(reconnect_delay)

            except Exception as e:
                logger.error(f"Unexpected error in hidraw monitor loop: {e}")
                self.error_count += 1
                time.sleep(0.1)

        logger.info("HidrawButtonMonitor loop ended")

    def _close_device(self):
        """Safely close the device for reconnection."""
        if self.device_fd is not None:
            try:
                os.close(self.device_fd)
            except:
                pass
            self.device_fd = None
        self.initialized = False
        self.device_path = None
        self.device_pid = None

    def _process_packet(self, data):
        """Parse HID packet and generate button events."""
        # Parse button states from packet
        buttons_l = struct.unpack('<I', data[8:12])[0]
        buttons_h = struct.unpack('<I', data[12:16])[0]

        # Check if button state changed
        if buttons_l == self.last_buttons_l and buttons_h == self.last_buttons_h:
            return

        timestamp = time.time()
        new_buttons = set()

        # Check ButtonsL
        for name, mask in self.BUTTONS_L.items():
            if buttons_l & mask:
                new_buttons.add(name)

        # Check ButtonsH
        for name, mask in self.BUTTONS_H.items():
            if buttons_h & mask:
                new_buttons.add(name)

        # Generate events for changed buttons
        with self.lock:
            # Buttons that were released
            for button in self.current_buttons - new_buttons:
                event = {
                    "button": button,
                    "pressed": False,
                    "timestamp": timestamp
                }
                try:
                    self.event_queue.put_nowait(event)
                except queue.Full:
                    # Queue full, discard oldest
                    try:
                        self.event_queue.get_nowait()
                        self.event_queue.put_nowait(event)
                    except:
                        pass

            # Buttons that were pressed
            for button in new_buttons - self.current_buttons:
                event = {
                    "button": button,
                    "pressed": True,
                    "timestamp": timestamp
                }
                try:
                    self.event_queue.put_nowait(event)
                except queue.Full:
                    try:
                        self.event_queue.get_nowait()
                        self.event_queue.put_nowait(event)
                    except:
                        pass

            self.current_buttons = new_buttons

        self.last_buttons_l = buttons_l
        self.last_buttons_h = buttons_h

    def get_events(self, max_events=10):
        """Get pending button events from the queue."""
        events = []
        with self.lock:
            for _ in range(max_events):
                try:
                    event = self.event_queue.get_nowait()
                    events.append(event)
                except queue.Empty:
                    break
        return events

    def get_button_state(self):
        """Get the current complete button state (all currently pressed buttons)."""
        with self.lock:
            return list(self.current_buttons)

    def get_status(self):
        """Get monitor status for diagnostics."""
        with self.lock:
            return {
                "running": self.running,
                "initialized": self.initialized,
                "device_path": self.device_path,
                "error_count": self.error_count,
                "queue_size": self.event_queue.qsize(),
                "current_buttons": list(self.current_buttons),
                "last_buttons_l": hex(self.last_buttons_l),
                "last_buttons_h": hex(self.last_buttons_h),
            }
