.. _HomeAssistant-Driver:

Home Assistant Driver
=====================

The Home Assistant driver enables VOLTTRON to read any data point from any Home Assistant controlled device.
**Currently Supported Write-Access Devices:**

- **Lights**: state (on/off) and brightness (0-255)
- **Thermostats**: state (off/heat/cool/auto) and temperature
- **Input Booleans**: state (on/off)
- **Fans**: state, percentage (0-100), preset_mode, direction, oscillating
- **Switches**: state (on/off)
- **Covers**: state (open/close/stop), position (0-100), tilt_position (0-100)
The following diagram shows interaction between platform driver agent and home assistant driver.

.. mermaid::

   sequenceDiagram
       HomeAssistant Driver->>HomeAssistant: Retrieve Entity Data (REST API)
       HomeAssistant-->>HomeAssistant Driver: Entity Data (Status Code: 200)
       HomeAssistant Driver->>PlatformDriverAgent: Publish Entity Data
       PlatformDriverAgent->>Controller Agent: Publish Entity Data

       Controller Agent->>HomeAssistant Driver: Instruct to Turn Off Light
       HomeAssistant Driver->>HomeAssistant: Send Turn Off Light Command (REST API)
       HomeAssistant-->>HomeAssistant Driver: Command Acknowledgement (Status Code: 200)

Pre-requisites
--------------
Before proceeding, find your Home Assistant IP address and long-lived access token from `here <https://developers.home-assistant.io/docs/auth_api/#long-lived-access-token>`_.

Clone the repository, start volttron, install the listener agent, and the platform driver agent.

- `Listener agent <https://volttron.readthedocs.io/en/main/introduction/platform-install.html#installing-and-running-agents>`_
- `Platform driver agent <https://volttron.readthedocs.io/en/main/agent-framework/core-service-agents/platform-driver/platform-driver-agent.html?highlight=platform%20driver%20isntall#configuring-the-platform-driver>`_

Configuration
--------------

After cloning, generate configuration files. Each device requires one device configuration file and one registry file.
Ensure your registry_config parameter in your device configuration file, links to correct registry config name in the
config store. For more details on how volttron platform driver agent works with volttron configuration store see,
`Platform driver configuration <https://volttron.readthedocs.io/en/main/agent-framework/driver-framework/platform-driver/platform-driver.html#configuration-and-installation>`_
Examples for lights and thermostats are provided below.

Device configuration
++++++++++++++++++++

Device configuration file contains the connection details to you home assistant instance and driver_type as "home_assistant"

.. code-block:: json

   {
       "driver_config": {
           "ip_address": "Your Home Assistant IP",
           "access_token": "Your Home Assistant Access Token",
           "port": "Your Port"
       },
       "driver_type": "home_assistant",
       "registry_config": "config://light.example.json",
       "interval": 30,
       "timezone": "UTC"
   }

Registry Configuration
+++++++++++++++++++++++

Registry file can contain one single device and its attributes or a logical group of devices and its
attributes. Each entry should include the full entity id of the device, including but not limited to home assistant provided prefix
such as "light.",  "climate." etc. The driver uses these prefixes to convert states into integers.
Like mentioned before, the driver can only control lights and thermostats but can get data from all devices
controlled by home assistant

Each entry in a registry file should also have a 'Entity Point' and a unique value for 'Volttron Point Name'. The 'Entity ID' maps to the device instance, the 'Entity Point' extracts the attribute or state, and 'Volttron Point Name' determines the name of that point as it appears in VOLTTRON.

Attributes can be located in the developer tools in the Home Assistant GUI.

.. image:: home-assistant.png


Below is an example file named light.example.json which has attributes of a single light instance with entity
id 'light.example':


.. code-block:: json

   [
       {
           "Entity ID": "light.example",
           "Entity Point": "state",
           "Volttron Point Name": "light_state",
           "Units": "On / Off",
           "Units Details": "on/off",
           "Writable": true,
           "Starting Value": true,
           "Type": "boolean",
           "Notes": "lights hallway"
       },
       {
           "Entity ID": "light.example",
           "Entity Point": "brightness",
           "Volttron Point Name": "light_brightness",
           "Units": "int",
           "Units Details": "light level",
           "Writable": true,
           "Starting Value": 0,
           "Type": "int",
           "Notes": "brightness control, 0 - 255"
       }
   ]


.. note::

When using a single registry file to represent a logical group of multiple physical entities, make sure the
"Volttron Point Name" is unique within a single registry file.

For example, if a registry file contains entities with
id  'light.instance1' and 'light.instance2' the entry for the attribute brightness for these two light instances could
have "Volttron Point Name" as 'light1/brightness' and 'light2/brightness' respectively. This would ensure that data
is posted to unique topic names and brightness data from light1 is not overwritten by light2 or vice-versa.

Example Thermostat Registry
***************************

For thermostats, the state is converted into numbers as follows: "0: Off, 2: heat, 3: Cool, 4: Auto",

.. code-block:: json

   [
       {
           "Entity ID": "climate.my_thermostat",
           "Entity Point": "state",
           "Volttron Point Name": "thermostat_state",
           "Units": "Enumeration",
           "Units Details": "0: Off, 2: heat, 3: Cool, 4: Auto",
           "Writable": true,
           "Starting Value": 1,
           "Type": "int",
           "Notes": "Mode of the thermostat"
       },
       {
           "Entity ID": "climate.my_thermostat",
           "Entity Point": "current_temperature",
           "Volttron Point Name": "volttron_current_temperature",
           "Units": "F",
           "Units Details": "Current Ambient Temperature",
           "Writable": true,
           "Starting Value": 72,
           "Type": "float",
           "Notes": "Current temperature reading"
       },
       {
           "Entity ID": "climate.my_thermostat",
           "Entity Point": "temperature",
           "Volttron Point Name": "set_temperature",
           "Units": "F",
           "Units Details": "Desired Temperature",
           "Writable": true,
           "Starting Value": 75,
           "Type": "float",
           "Notes": "Target Temp"
       }
   ]



Example Switch Registry
***************************

Switches are simple on/off devices such as outlets, relays, or other switched devices.

**Switch State Values:**

- **0**: Turn off the switch
- **1**: Turn on the switch

.. code-block:: json

   [
       {
           "Entity ID": "switch.living_room_outlet",
           "Entity Point": "state",
           "Volttron Point Name": "outlet_state",
           "Units": "On / Off",
           "Units Details": "off: 0, on: 1",
           "Writable": true,
           "Starting Value": 0,
           "Type": "int",
           "Notes": "Control outlet on/off state"
       }
   ]

**Example: Multiple Switches**

.. code-block:: json

   [
       {
           "Entity ID": "switch.living_room_outlet",
           "Entity Point": "state",
           "Volttron Point Name": "living_room_outlet_state",
           "Units": "On / Off",
           "Units Details": "off: 0, on: 1",
           "Writable": true,
           "Starting Value": 0,
           "Type": "int",
           "Notes": "Living room outlet control"
       },
       {
           "Entity ID": "switch.bedroom_outlet",
           "Entity Point": "state",
           "Volttron Point Name": "bedroom_outlet_state",
           "Units": "On / Off",
           "Units Details": "off: 0, on: 1",
           "Writable": true,
           "Starting Value": 0,
           "Type": "int",
           "Notes": "Bedroom outlet control"
       }
   ]

Example Cover Registry
***************************

Covers include blinds, shades, curtains, garage doors, and other similar devices. The Home Assistant driver supports
comprehensive control of covers including state (open/close/stop), position, and tilt position.

**Cover State Values:**

- **0**: Close the cover
- **1**: Open the cover
- **2**: Stop the cover (halt current movement)

**Cover Positions:**

- **position**: 0-100, where 0=fully closed and 100=fully open
- **tilt_position**: 0-100, for covers that support tilting (e.g., venetian blinds)

**Supported Cover Device Classes:**

The driver supports all Home Assistant cover types including: awning, blind, curtain, damper, door, garage, gate, shade, shutter, and window.

**Example: Blinds with Position and Tilt Control**

.. code-block:: json

   [
       {
           "Entity ID": "cover.living_room_blinds",
           "Entity Point": "state",
           "Volttron Point Name": "blinds_state",
           "Units": "Enumeration",
           "Units Details": "0: Close, 1: Open, 2: Stop",
           "Writable": true,
           "Starting Value": 0,
           "Type": "int",
           "Notes": "Control to open/close/stop the blinds"
       },
       {
           "Entity ID": "cover.living_room_blinds",
           "Entity Point": "current_position",
           "Volttron Point Name": "blinds_position",
           "Units": "Percentage",
           "Units Details": "0-100, where 0=closed and 100=fully open",
           "Writable": true,
           "Starting Value": 0,
           "Type": "int",
           "Notes": "Position control (0-100)"
       },
       {
           "Entity ID": "cover.living_room_blinds",
           "Entity Point": "current_tilt_position",
           "Volttron Point Name": "blinds_tilt",
           "Units": "Percentage",
           "Units Details": "0-100, tilt angle control",
           "Writable": true,
           "Starting Value": 0,
           "Type": "int",
           "Notes": "Tilt position for venetian blinds (0-100)"
       }
   ]

**Example: Garage Door**

.. code-block:: json

   [
       {
           "Entity ID": "cover.garage_door",
           "Entity Point": "state",
           "Volttron Point Name": "garage_state",
           "Units": "Enumeration",
           "Units Details": "0: Close, 1: Open, 2: Stop",
           "Writable": true,
           "Starting Value": 0,
           "Type": "int",
           "Notes": "Garage door control"
       },
       {
           "Entity ID": "cover.garage_door",
           "Entity Point": "current_position",
           "Volttron Point Name": "garage_position",
           "Units": "Percentage",
           "Units Details": "0-100, door position",
           "Writable": true,
           "Starting Value": 0,
           "Type": "int",
           "Notes": "Position allows partial opening"
       }
   ]

.. note::

   Not all covers support all features. For example:

   - Some covers may only support open/close but not position control
   - Tilt position is only available for covers like venetian blinds that support tilting
   - When a feature is not supported, the attribute will not be available in Home Assistant

   Check your specific device's capabilities in the Home Assistant Developer Tools > States panel.

Example Fan Registry
***************************

Fans are multi-function devices that can be controlled via:

- **state**: 0 = off, 1 = on
- **percentage**: 0-100, speed level
- **preset_mode**: device-specific presets (e.g., auto, sleep, nature)
- **direction**: forward / reverse
- **oscillating**: 0 = off, 1 = on (or False/True)

.. code-block:: json

   [
       {
           "Entity ID": "fan.living_room_fan",
           "Entity Point": "state",
           "Volttron Point Name": "fan_state",
           "Units": "On / Off",
           "Units Details": "off: 0, on: 1",
           "Writable": true,
           "Starting Value": 0,
           "Type": "int",
           "Notes": "Power on/off"
       },
       {
           "Entity ID": "fan.living_room_fan",
           "Entity Point": "percentage",
           "Volttron Point Name": "fan_speed",
           "Units": "%",
           "Units Details": "0-100",
           "Writable": true,
           "Starting Value": 0,
           "Type": "int",
           "Notes": "Speed percentage"
       },
       {
           "Entity ID": "fan.living_room_fan",
           "Entity Point": "preset_mode",
           "Volttron Point Name": "fan_preset",
           "Units": "Preset",
           "Units Details": "device-specific (e.g., auto, sleep)",
           "Writable": true,
           "Starting Value": "",
           "Type": "string",
           "Notes": "Preset mode"
       },
       {
           "Entity ID": "fan.living_room_fan",
           "Entity Point": "direction",
           "Volttron Point Name": "fan_direction",
           "Units": "Direction",
           "Units Details": "forward, reverse",
           "Writable": true,
           "Starting Value": "forward",
           "Type": "string",
           "Notes": "Rotation direction"
       },
       {
           "Entity ID": "fan.living_room_fan",
           "Entity Point": "oscillating",
           "Volttron Point Name": "fan_oscillating",
           "Units": "On / Off",
           "Units Details": "off: 0, on: 1",
           "Writable": true,
           "Starting Value": 0,
           "Type": "int",
           "Notes": "Oscillation control"
       }
   ]

.. note::

   Not all fans support all points. Check the fan entity in Home Assistant Developer Tools > States to see available attributes (e.g., supported preset modes or direction).


Transfer the registers files and the config files into the VOLTTRON config store using the commands below:

.. code-block:: bash

   vctl config store platform.driver light.example.json HomeAssistant_Driver/light.example.json
   vctl config store platform.driver devices/BUILDING/ROOM/light.example HomeAssistant_Driver/light.example.config

Upon completion, initiate the platform driver. Utilize the listener agent to verify the driver output:

.. code-block:: bash

   2023-09-12 11:37:00,226 (listeneragent-3.3 211531) __main__ INFO: Peer: pubsub, Sender: platform.driver:, Bus: , Topic: devices/BUILDING/ROOM/light.example/all, Headers: {'Date': '2023-09-12T18:37:00.224648+00:00', 'TimeStamp': '2023-09-12T18:37:00.224648+00:00', 'SynchronizedTimeStamp': '2023-09-12T18:37:00.000000+00:00', 'min_compatible_version': '3.0', 'max_compatible_version': ''}, Message:
   [{'light_brightness': 254, 'state': 'on'},
    {'light_brightness': {'type': 'integer', 'tz': 'UTC', 'units': 'int'},
     'state': {'type': 'integer', 'tz': 'UTC', 'units': 'On / Off'}}]

Running Tests
+++++++++++++++++++++++
The Home Assistant driver includes comprehensive unit tests and integration tests for all supported device types.

**Unit Tests (No Home Assistant Required)**

Unit tests use mocking and don't require a live Home Assistant instance. They test all device control methods:

.. code-block:: bash

    # Run all unit tests
    pytest services/core/PlatformDriverAgent/tests/test_home_assistant.py::TestFanMocked -v
    pytest services/core/PlatformDriverAgent/tests/test_home_assistant.py::TestSwitchMocked -v
    pytest services/core/PlatformDriverAgent/tests/test_home_assistant.py::TestCoverMocked -v

**Integration Tests (Require Home Assistant)**

Integration tests require a live Home Assistant instance with actual devices/helpers.

**Basic Integration Tests:**

1. Create a helper toggle in Home Assistant: **Settings > Devices & services > Helpers > Create Helper > Toggle**
2. Name it **volttrontest**
3. Set test configuration variables in ``test_home_assistant.py``:

.. code-block:: python

    HOMEASSISTANT_TEST_IP = "192.168.1.100"
    ACCESS_TOKEN = "your_long_lived_access_token"
    PORT = "8123"

4. Run basic tests:

.. code-block:: bash

    pytest services/core/PlatformDriverAgent/tests/test_home_assistant.py::test_get_point -v
    pytest services/core/PlatformDriverAgent/tests/test_home_assistant.py::test_data_poll -v
    pytest services/core/PlatformDriverAgent/tests/test_home_assistant.py::test_set_point -v

**Fan Integration Tests:**

1. Set ``FAN_TEST_ENTITY_ID`` to your fan entity (e.g., ``"fan.living_room_fan"``)
2. Run fan tests:

.. code-block:: bash

    pytest services/core/PlatformDriverAgent/tests/test_home_assistant.py -k "fan" -v

**Switch Integration Tests:**

1. Set ``SWITCH_TEST_ENTITY_ID`` to your switch entity (e.g., ``"switch.living_room_outlet"``)
2. Run switch tests:

.. code-block:: bash

    pytest services/core/PlatformDriverAgent/tests/test_home_assistant.py -k "switch" -v

**Cover Integration Tests:**

1. Create a cover helper or use an existing cover device
2. Set ``COVER_TEST_ENTITY_ID`` to your cover entity (e.g., ``"cover.living_room_blinds"``)
3. Run cover tests:

.. code-block:: bash

    pytest services/core/PlatformDriverAgent/tests/test_home_assistant.py -k "cover" -v

**Run All Tests:**

.. code-block:: bash

    # Run all tests (unit + integration)
    pytest services/core/PlatformDriverAgent/tests/test_home_assistant.py -v

**Test Summary (high level):**

- **Unit Tests (mocked; no Home Assistant needed):** cover fan, switch, and cover write-access and validation.
- **Integration Tests (require Home Assistant):** basic toggle helper + device-specific fan/switch/cover flows when entity IDs and credentials are provided.

Refer to the individual test classes in ``services/core/PlatformDriverAgent/tests/test_home_assistant.py`` for the exact test coverage per device type.