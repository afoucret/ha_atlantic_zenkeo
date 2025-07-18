"""Python implementation of the Atlantic Zenkeo AC protocol."""
import asyncio
import logging
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Callable

_LOGGER = logging.getLogger(__name__)


class Limits(Enum):
    """AC limits."""

    OFF = 0
    ONLY_VERTICAL = 1


class FanSpeed(Enum):
    """AC fan speeds."""

    MAX = 0
    MID = 1
    MIN = 2
    AUTO = 3


class Mode(Enum):
    """AC modes."""

    SMART = 0
    COOL = 1
    HEAT = 2
    FAN = 3
    DRY = 4


@dataclass
class ZenkeoState:
    """Dataclass to hold the state of the AC unit."""

    current_temperature: int
    target_temperature: int
    fan_speed: FanSpeed
    mode: Mode
    health: bool
    power: bool


class ZenkeoAC:
    """Represents a Zenkeo AC unit."""

    def __init__(self, ip: str, mac: str, port: int = 56800, timeout: int = 500):
        """Initialize the AC unit."""
        self.ip = ip
        self.port = port
        self.mac = mac.replace(":", "").upper()
        self._seq = 0
        self._reader = None
        self._writer = None
        self.timeout = timeout

    async def _send_request(self, create_command: Callable[[int], bytes]) -> bytes:
        seq = self._get_seq()
        cmd = create_command(int(seq.split(" ")[-1], 16))

        response = await self._send_command(cmd)
        return response

    async def _connect(self):
        """Connect to the AC unit."""
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.ip, self.port), timeout=10
        )

    async def _send_command(self, command: bytes) -> bytes:
        """Send a command to the AC unit and return the response."""
        if not self._writer or self._writer.is_closing():
            await self._connect()

        if self._writer is None or self._reader is None:
            raise ConnectionError("Failed to establish connection to AC unit.")

        _LOGGER.debug("Sending command: %s", command.hex())
        self._writer.write(command)
        await self._writer.drain()

        response = await self._reader.read(1024)
        _LOGGER.warning("RAW AC RESPONSE: %s", response.hex())
        return response

    def _order_byte(self, n: int) -> str:
        val = n % 256
        if val < 16:
            return f"00 00 00 0{val:x}"
        else:
            return f"00 00 00 {val:x}"

    def _len4(self, cmd: str) -> str:
        length = len(bytes.fromhex(cmd.replace(" ", "")))
        return self._order_byte(length)

    def _build_command(self, *args: str) -> bytes:
        """Build a command from a series of hex strings."""
        return bytes.fromhex("".join(args).replace(" ", ""))

    def _get_seq(self) -> str:
        """Get the next sequence number."""
        seq_hex = f"{self._seq:02x}"
        self._seq = (self._seq + 1) % 256
        return f"00 00 00 {seq_hex}"

    def _mac_to_hex(self) -> str:
        """Convert the MAC address to the required hex format."""
        return " ".join([f"{ord(c):02x}" for c in self.mac]) + " 00 00 00 00"

    def _append_checksum(self, command_str: str) -> str:
        """Append the checksum to a command string."""
        
        checksum = (
            sum(
                int(c, 16) * (i % 2 + 1)
                for i, c in enumerate(command_str.replace(" ", ""))
            )
            - 2 * 255
        ) & 0xFF
        return f"{command_str} {checksum:02x}"

    def _parse_state(self, response: bytes) -> ZenkeoState | None:
        """Parse the state from a response."""
        try:
            # The state payload starts with ff ff 22 00
            payload_start = response.find(b"\xff\xff\x22\x00")
            if payload_start == -1:
                _LOGGER.debug(
                    "State payload (ff ff 22 00) not found in response. Full response: %s",
                    response.hex(),
                )
                return None

            # The data to parse starts right after the marker.
            data_start = payload_start + 4
            
            # Define the structure based on the TS library's binary-parser.
            # > = big-endian, H = unsigned short (2 bytes), x = padding
            data_format = ">8xH8xHHHHH2xH"
            
            expected_size = struct.calcsize(data_format)
            
            if len(response) < data_start + expected_size:
                _LOGGER.debug(
                    "Not enough data for state parsing. Full response: %s", response.hex()
                )
                return None

            unpacked_data = struct.unpack(data_format, response[data_start : data_start + expected_size])
            
            (
                current_temp,
                mode,
                fan_speed,
                limits, # This is unused for now but parsed for completeness
                power,
                health,
                target_temp,
            ) = unpacked_data

            return ZenkeoState(
                current_temperature=current_temp,
                target_temperature=target_temp + 16,
                fan_speed=FanSpeed(fan_speed),
                mode=Mode(mode),
                health=bool(health % 2),
                power=bool(power % 2),
            )
        except (struct.error, ValueError) as e:
            _LOGGER.error(
                "Failed to parse state from response. Error: %s. Full response: %s",
                e,
                response.hex(),
            )
            return None

    async def get_state(self) -> ZenkeoState | None:
        """Get the current state of the AC."""
        # Send a dummy set_state command to trigger a state response
        state_command = (
            f"ff ff 22 00 00 00 00 00 00 01 4d 5f 00 00 00 00 00 00 00 00 00 00 "
            f"00 0{Mode.COOL.value} "
            f"00 0{FanSpeed.AUTO.value} "
            f"00 0{Limits.OFF.value} "
            f"00 0{0} "  # Power off
            f"00 0{0} "  # Health off
            f"00 00 00 0{(21 - 16):x}" # Target temp 21
        )
        state_command = self._append_checksum(state_command)
        response = await self._send_request(lambda seq: self._build_command(
            "00 00 27 14 00 00 00 00",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            self._mac_to_hex(),
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            self._order_byte(seq),
            self._len4(state_command),
            state_command,
        ))
        return self._parse_state(response)

    

    async def hello(self):
        """Send a hello command to the AC."""
        return await self._send_request(lambda seq: self._build_command(
            "00 00 27 14 00 00 00 00",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            self._mac_to_hex(),
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            self._order_byte(seq),
            self._len4("ff ff 0a 00 00 00 00 00 00 01 4d 01 59"),
            "ff ff 0a 00 00 00 00 00 00 01 4d 01 59",
        ))

    async def init(self):
        """Send an init command to the AC."""
        return await self._send_request(lambda seq: self._build_command(
            "00 00 27 14 00 00 00 00",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            self._mac_to_hex(),
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            self._order_byte(seq),
            self._len4("ff ff 08 00 00 00 00 00 00 73 7b"),
            "ff ff 08 00 00 00 00 00 00 73 7b",
        ))

    async def turn_on(self):
        """Turn the AC on."""
        return await self._send_request(lambda seq: self._build_command(
            "00 00 27 14 00 00 00 00",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            self._mac_to_hex(),
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            self._order_byte(seq),
            self._len4("ff ff 0a 00 00 00 00 00 00 01 4d 02 5a"),
            "ff ff 0a 00 00 00 00 00 00 01 4d 02 5a",
        ))

    async def turn_off(self):
        """Turn the AC off."""
        return await self._send_request(lambda seq: self._build_command(
            "00 00 27 14 00 00 00 00",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            self._mac_to_hex(),
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            self._order_byte(seq),
            self._len4("ff ff 0a 00 00 00 00 00 00 01 4d 03 5b"),
            "ff ff 0a 00 00 00 00 00 00 01 4d 03 5b",
        ))

    async def change_state(
        self,
        power: bool,
        mode: Mode,
        fan_speed: FanSpeed,
        target_temp: int,
        health: bool = False,
        limits: Limits = Limits.OFF,
    ):
        """Set the state of the AC."""
        state_command = (
            f"ff ff 22 00 00 00 00 00 00 01 4d 5f 00 00 00 00 00 00 00 00 00 00 "
            f"00 0{mode.value} "
            f"00 0{fan_speed.value} "
            f"00 0{limits.value} "
            f"00 0{1 if power else 0} "
            f"00 0{1 if health else 0} "
            f"00 00 00 0{(target_temp - 16):x}"
        )
        state_command = self._append_checksum(state_command)
        response = await self._send_request(lambda seq: self._build_command(
            "00 00 27 14 00 00 00 00",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            self._mac_to_hex(),
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            self._order_byte(seq),
            self._len4(state_command),
            state_command,
        ))
        return self._parse_state(response)
