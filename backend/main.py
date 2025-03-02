import asyncio
from datetime import datetime
from uuid import uuid4
import os
import time
import buttplug
from buttplug.errors.client import ScanNotRunningError
from dotenv import load_dotenv
import websockets
import sys
import json
import logging
import yaml

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
logger.addHandler(stream_handler)

load_dotenv('.env')

# Fix for Windows event loop policy (Python 3.8+)
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

QUEUE = asyncio.Queue()
active_task = None  # Track active queue processing task

WS_ADDRESS = os.getenv('WS_ADDRESS')
INTIFACE_ENGINE_CLIENT_NAME = os.getenv('INTIFACE_ENGINE_CLIENT_NAME', "Python-App")
INTIFACE_ENGINE_WS_URL = "ws://127.0.0.1:15345"

client = buttplug.client.Client(INTIFACE_ENGINE_CLIENT_NAME)
connector = buttplug.connectors.WebsocketConnector(INTIFACE_ENGINE_WS_URL)

devices = {}
last_battery_check = None
BATTERY_CHECK_RUNNING = True
battery_levels = {}
last_heartbeat = 0
sim_running = True


async def handle_queue(websocket):
    """Process messages from the queue and send them to the WebSocket server."""
    global active_task
    while not QUEUE.empty():
        message = await QUEUE.get()  # Get a JSON dict from the queue
        json_message = json.dumps(message)  # Convert to JSON string
        await websocket.send(json_message)
        print(f"Sent: {json_message}")
        await asyncio.sleep(1)  # Simulating processing time

    active_task = None  # Reset task when queue is empty


async def monitor_queue(websocket):
    """Monitor the queue and start handle_queue if there are items."""
    global active_task
    while True:
        if not QUEUE.empty() and active_task is None:
            print("Starting queue processing...")
            active_task = asyncio.create_task(handle_queue(websocket))
        await asyncio.sleep(0.5)  # Avoid excessive looping


async def check_battery_levels(buttplug_client):
    global last_battery_check, BATTERY_CHECK_RUNNING
    while BATTERY_CHECK_RUNNING:
        if last_battery_check is None:
            last_battery_check = time.time()
            logger.debug("init: check_battery_levels")
            logger.debug("check_battery_levels: exec")
            for device_index, device in buttplug_client.devices.items():
                if device.name == "Lovense Hush":
                    battery_sensor = device.sensors[0]
                    current_level = await battery_sensor.read()
                    now_dt = datetime.now()
                    battery_levels[device_index] = (current_level[0], now_dt.strftime("%d.%m.%Y %H:%M:%S"))

        else:
            if int(time.time() - last_battery_check) >= 10:
                # print("check_battery_levels: exec")
                for device_index, device in buttplug_client.devices.items():
                    if device.name == "Lovense Hush":
                        battery_sensor = device.sensors[0]
                        try:
                            current_level = await battery_sensor.read()
                            now_dt = datetime.now()
                            battery_levels[device_index] = (current_level[0], now_dt.strftime("%d.%m.%Y %H:%M:%S"))
                        except buttplug.errors.server.DeviceServerError:
                            print(" - no devices")
                            pass

                last_battery_check = time.time()
        await asyncio.sleep(1)


def set_devices_config(devices_dict):
    with open('devices.yaml', 'w') as file:
        yaml.dump(devices_dict, file, sort_keys=False)


def get_devices_config():
    with open('devices.yaml') as file:
        content = yaml.load(file, Loader=yaml.Loader)
        return content


async def enumerate_devices(buttplug_client):
    logger.debug("async: enumerate_devices")
    for device_index, buttplug_device in buttplug_client.devices.items():
        buttplug_device.logger.setLevel(logging.DEBUG)

        battery_level = "N/A"
        battery_check_t = None
        if buttplug_device.name == "Lovense Hush":
            battery_level_ = await buttplug_device.sensors[0].read()
            battery_level = battery_level_[0]
            battery_check_t = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        devices[device_index] = {
            "name": buttplug_device.name,
            "uuid": str(uuid4()),
            "device_index": device_index,
            "battery": {
                "level": battery_level,
                "last_check": battery_check_t
            },
            "last_connected": datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        }

    await devices_to_ws(devices)
    set_devices_config(devices)


async def devices_to_ws(devices_dict_data):
    uri = "ws://localhost:3000"  # Replace with your server's WebSocket URL if different
    async with websockets.connect(uri) as websocket:
        # logger.debug("ws-client      : Connected to WebSocket server")

        devices_dict = {
            "target": "devices",
            "data": devices_dict_data
        }
        # Send a message to the WebSocket server
        message = json.dumps(devices_dict)

        logger.info(f"Sending: {message}")
        await websocket.send(message)

        try:
            # Wait for a response from the server
            response = await websocket.recv()
            logger.info(f"Received: {response}")

        except websockets.exceptions.ConnectionClosedError:
            pass
        await websocket.close()


async def connect_buttplug(buttplug_client):
    try:
        if not connector.connected:
            logger.debug("buttplug-client: connecting...")
            await buttplug_client.connect(connector=connector)
            logger.info("buttplug-client: connected to Buttplug server.")
            if len(buttplug_client.devices) == 0:
                await buttplug_client.start_scanning()
                await asyncio.sleep(3)
                try:
                    await buttplug_client.stop_scanning()
                    await enumerate_devices(buttplug_client)
                except ScanNotRunningError:
                    pass
                except TypeError as e:
                    logger.error(e.args)
                except buttplug.errors.client.DisconnectedError as e:
                    logger.error(f"DisconnectedError: {e.message}")

            else:
                await enumerate_devices(buttplug_client)

        elif buttplug_client.connected:
            logger.info("buttplug-client: already connected to Buttplug server.")
            if len(buttplug_client.devices) == 0:
                await buttplug_client.start_scanning()
                await asyncio.sleep(3)
                try:
                    await buttplug_client.stop_scanning()
                    await enumerate_devices(buttplug_client)
                except ScanNotRunningError:
                    pass
                except TypeError as e:
                    logger.error(e.args)
                except buttplug.errors.client.DisconnectedError as e:
                    logger.error(f"DisconnectedError: {e.message}")

            else:
                await enumerate_devices(buttplug_client)

        while buttplug_client.connected:
            await asyncio.sleep(5)

    except asyncio.CancelledError:
        logger.info("connect_buttplug() was cancelled. Cleaning up...")
        await buttplug_client.disconnect()  # Gracefully disconnect
        raise  # Re-raise to ensure proper task cancellation handling

    except buttplug.errors.client.ServerNotFoundError as e:
        logger.error(f"ServerNotFoundError: {e}")

    finally:
        logger.info("Exiting connect_buttplug()")
        await asyncio.sleep(5)
        logger.debug("retrying after 5 seconds...")
        asyncio.create_task(connect_buttplug(buttplug_client))


async def receive_messages(websocket):
    """Receive messages from the WebSocket server."""
    try:
        while True:
            response = await websocket.recv()
            try:
                json_response: dict = json.loads(response)

                if "devices" in json_response.keys():
                    logger.debug("getting devices...")
                    asyncio.create_task(connect_buttplug(client))
                if "target" in json_response.keys():
                    target = json_response["target"]
                    if target == "battery_level":
                        if len(list(battery_levels.keys())) > 0:
                            current_device_index = None
                            for device_, device_data in devices.items():
                                if device_data.get('uuid') == json_response["device_uuid"]:
                                    current_device_index = device_data.get('device_index')

                            if current_device_index is not None:
                                for battery_level_k, battery_level_item in battery_levels.items():
                                    if battery_level_k == current_device_index:
                                        battery_level_value = battery_level_item[0]
                                        battery_level_last_check = battery_level_item[1]

                                        file_devices: dict = get_devices_config()
                                        file_devices[current_device_index]["battery"]["level"] = \
                                            battery_level_value
                                        file_devices[current_device_index]["battery"]["last_check"] = \
                                            battery_level_last_check

                                        set_devices_config(file_devices)

                                        await websocket.send(message=json.dumps({
                                            "target": "battery_level_result",
                                            "data": {
                                                "uuid": json_response["device_uuid"],
                                                "level": battery_level_value,
                                                "last_check": battery_level_last_check
                                            }
                                        }))

                # print(f"WS  : Received: {response}")
            except json.decoder.JSONDecodeError:
                logger.error("NOT_JSON: "+response)
                pass
    except websockets.exceptions.ConnectionClosed:
        logger.error("WebSocket connection closed. Reconnecting...")


async def websocket_client():
    """Manages the WebSocket connection and restarts on failure."""
    uri = WS_ADDRESS  # Adjust the WebSocket server URL
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                logger.debug("ws-client      : Connected to WebSocket server")

                # Start monitoring the queue
                asyncio.create_task(monitor_queue(websocket))

                # Start receiving messages from the server
                await receive_messages(websocket)
        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError):
            logger.error("Connection lost. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)  # Wait before reconnecting


async def simulate_incoming_messages():
    global last_heartbeat
    """Simulates adding messages to the queue dynamically."""
    while True:
        await asyncio.sleep(10)  # Add a message every 10 seconds

        current_time = time.time()

        await QUEUE.put({
            "type": "heartbeat",
            "current_time": current_time,
            "last_heartbeat": last_heartbeat,
            "diff": current_time - last_heartbeat
        })

        last_heartbeat = time.time()
        logger.debug("Added a message to the queue")


async def main():
    """Runs the WebSocket client and keeps it alive."""
    tasks = [
        websocket_client(),
        check_battery_levels(client),
    ]

    await asyncio.gather(*tasks)

    while True:
        await asyncio.sleep(60)  # Keep the main task alive

# Run the event loop indefinitely
asyncio.run(main())
