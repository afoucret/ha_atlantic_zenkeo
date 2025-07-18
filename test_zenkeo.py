import asyncio
import logging
import argparse
from custom_components.atlantic_zenkeo.pyzenkeo import ZenkeoAC, Mode, FanSpeed
from getmac import get_mac_address

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
_LOGGER.addHandler(handler)

async def test_ac_unit(ip: str):
    _LOGGER.info(f"Attempting to get MAC address for {ip}...")
    mac_address = get_mac_address(ip=ip)

    if not mac_address:
        _LOGGER.error(f"Could not retrieve MAC address for {ip}. Please ensure the device is on and reachable.")
        return

    _LOGGER.info(f"Found MAC address: {mac_address}")
    ac = ZenkeoAC(ip, mac_address)

    try:
        _LOGGER.info("Sending hello command...")
        response = await ac.hello()
        _LOGGER.info(f"Hello response: {response.hex()}")

        _LOGGER.info("Sending init command...")
        response = await ac.init()
        _LOGGER.info(f"Init response: {response.hex()}")

        _LOGGER.info("Getting state...")
        state = await ac.get_state()
        if state:
            _LOGGER.info(f"Current state: {state}")
        else:
            _LOGGER.warning("Could not retrieve state.")

        _LOGGER.info("Turning on AC...")
        await ac.turn_on()
        _LOGGER.info("AC turned on.")

        _LOGGER.info("Changing state to Cool, Fan Auto, Target 22C...")
        await ac.change_state(power=True, mode=Mode.COOL, fan_speed=FanSpeed.AUTO, target_temp=22)
        _LOGGER.info("State changed.")

        _LOGGER.info("Getting state after change...")
        state = await ac.get_state()
        if state:
            _LOGGER.info(f"Current state: {state}")
        else:
            _LOGGER.warning("Could not retrieve state after change.")

        _LOGGER.info("Turning off AC...")
        await ac.turn_off()
        _LOGGER.info("AC turned off.")

        _LOGGER.info("Getting state after turn off...")
        state = await ac.get_state()
        if state:
            _LOGGER.info(f"Current state: {state}")
        else:
            _LOGGER.warning("Could not retrieve state after turn off.")

    except asyncio.TimeoutError:
        _LOGGER.error(f"Connection to {ip} timed out.")
    except ConnectionError as e:
        _LOGGER.error(f"Connection error: {e}")
    except Exception as e:
        _LOGGER.exception(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Atlantic Zenkeo AC unit.")
    parser.add_argument("ip", type=str, help="IP address of the AC unit")
    args = parser.parse_args()

    asyncio.run(test_ac_unit(args.ip))