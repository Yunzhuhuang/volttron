# -*- coding: utf-8 -*- {{{
# ===----------------------------------------------------------------------===
#
#                 Component of Eclipse VOLTTRON
#
# ===----------------------------------------------------------------------===
#
# Copyright 2023 Battelle Memorial Institute
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy
# of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# ===----------------------------------------------------------------------===
# }}}


import random
from math import pi
import json
import sys
from platform_driver.interfaces import BaseInterface, BaseRegister, BasicRevert
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent
import logging
import requests
from requests import get

_log = logging.getLogger(__name__)
type_mapping = {"string": str,
                "int": int,
                "integer": int,
                "float": float,
                "bool": bool,
                "boolean": bool}


class HomeAssistantRegister(BaseRegister):
    def __init__(self, read_only, pointName, units, reg_type, attributes, entity_id, entity_point, default_value=None,
                 description=''):
        super(HomeAssistantRegister, self).__init__("byte", read_only, pointName, units, description='')
        self.reg_type = reg_type
        self.attributes = attributes
        self.entity_id = entity_id
        self.value = None
        self.entity_point = entity_point


def _post_method(url, headers, data, operation_description):
    err = None
    try:
        _log.info("Calling Home Assistant service: url=%s, data=%s, operation=%s", url, data, operation_description)
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            _log.info(f"Success: {operation_description}")
        else:
            err = f"Failed to {operation_description}. Status code: {response.status_code}. " \
                  f"Response: {response.text}"

    except requests.RequestException as e:
        err = f"Error when attempting - {operation_description} : {e}"
    if err:
        _log.error(err)
        raise Exception(err)


class Interface(BasicRevert, BaseInterface):
    def __init__(self, **kwargs):
        super(Interface, self).__init__(**kwargs)
        self.point_name = None
        self.ip_address = None
        self.access_token = None
        self.port = None
        self.units = None

    def configure(self, config_dict, registry_config_str):
        self.ip_address = config_dict.get("ip_address", None)
        self.access_token = config_dict.get("access_token", None)
        self.port = config_dict.get("port", None)

        # Check for None values
        if self.ip_address is None:
            _log.error("IP address is not set.")
            raise ValueError("IP address is required.")
        if self.access_token is None:
            _log.error("Access token is not set.")
            raise ValueError("Access token is required.")
        if self.port is None:
            _log.error("Port is not set.")
            raise ValueError("Port is required.")

        self.parse_config(registry_config_str)

    def get_point(self, point_name):
        register = self.get_register_by_name(point_name)

        entity_data = self.get_entity_data(register.entity_id)
        if register.point_name == "state":
            result = entity_data.get("state", None)
            return result
        else:
            value = entity_data.get("attributes", {}).get(f"{register.point_name}", 0)
            return value

    def _set_point(self, point_name, value):
        register = self.get_register_by_name(point_name)
        if register.read_only:
            raise IOError(
                "Trying to write to a point configured read only: " + point_name)
        register.value = register.reg_type(value)  # setting the value
        entity_point = register.entity_point
        # Changing lights values in home assistant based off of register value.
        if "light." in register.entity_id:
            if entity_point == "state":
                if isinstance(register.value, int) and register.value in [0, 1]:
                    if register.value == 1:
                        self.turn_on_lights(register.entity_id)
                    elif register.value == 0:
                        self.turn_off_lights(register.entity_id)
                else:
                    error_msg = f"State value for {register.entity_id} should be an integer value of 1 or 0"
                    _log.info(error_msg)
                    raise ValueError(error_msg)

            elif entity_point == "brightness":
                if isinstance(register.value, int) and 0 <= register.value <= 255:  # Make sure its int and within range
                    self.change_brightness(register.entity_id, register.value)
                else:
                    error_msg = "Brightness value should be an integer between 0 and 255"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            else:
                error_msg = f"Unexpected point_name {point_name} for register {register.entity_id}"
                _log.error(error_msg)
                raise ValueError(error_msg)

        elif "input_boolean." in register.entity_id:
            if entity_point == "state":
                if isinstance(register.value, int) and register.value in [0, 1]:
                    if register.value == 1:
                        self.set_input_boolean(register.entity_id, "on")
                    elif register.value == 0:
                        self.set_input_boolean(register.entity_id, "off")
                else:
                    error_msg = f"State value for {register.entity_id} should be an integer value of 1 or 0"
                    _log.info(error_msg)
                    raise ValueError(error_msg)
            else:
                _log.info(f"Currently, input_booleans only support state")

        # Changing fan values.
        elif "fan." in register.entity_id:
            if entity_point == "state":
                if isinstance(register.value, int) and register.value in [0, 1]:
                    if register.value == 1:
                        self.turn_on_fan(register.entity_id)
                    elif register.value == 0:
                        self.turn_off_fan(register.entity_id)
                else:
                    error_msg = f"State value for {register.entity_id} should be an integer value of 1 or 0"
                    _log.error(error_msg)
                    raise ValueError(error_msg)

            elif entity_point == "percentage":
                if isinstance(register.value, int) and 0 <= register.value <= 100:
                    self.set_fan_percentage(register.entity_id, register.value)
                else:
                    error_msg = "Fan percentage value should be an integer between 0 and 100"
                    _log.error(error_msg)
                    raise ValueError(error_msg)

            elif entity_point == "preset_mode":
                if isinstance(register.value, str) and register.value:
                    self.set_fan_preset_mode(register.entity_id, register.value)
                else:
                    error_msg = "Fan preset_mode value should be a non-empty string"
                    _log.error(error_msg)
                    raise ValueError(error_msg)

            elif entity_point == "direction":
                if isinstance(register.value, str) and register.value in ["forward", "reverse"]:
                    self.set_fan_direction(register.entity_id, register.value)
                else:
                    error_msg = "Fan direction value should be 'forward' or 'reverse'"
                    _log.error(error_msg)
                    raise ValueError(error_msg)

            elif entity_point == "oscillating":
                if isinstance(register.value, int) and register.value in [0, 1]:
                    self.set_fan_oscillation(register.entity_id, bool(register.value))
                elif isinstance(register.value, bool):
                    self.set_fan_oscillation(register.entity_id, register.value)
                else:
                    error_msg = "Fan oscillating value should be 0, 1, True, or False"
                    _log.error(error_msg)
                    raise ValueError(error_msg)

            else:
                error_msg = f"Unexpected entity_point {entity_point} for fan {register.entity_id}. " \
                            f"Supported: state, percentage, preset_mode, direction, oscillating"
                _log.error(error_msg)
                raise ValueError(error_msg)

        # Changing thermostat values.
        elif "climate." in register.entity_id:
            if entity_point == "state":
                if isinstance(register.value, int) and register.value in [0, 2, 3, 4]:
                    if register.value == 0:
                        self.change_thermostat_mode(entity_id=register.entity_id, mode="off")
                    elif register.value == 2:
                        self.change_thermostat_mode(entity_id=register.entity_id, mode="heat")
                    elif register.value == 3:
                        self.change_thermostat_mode(entity_id=register.entity_id, mode="cool")
                    elif register.value == 4:
                        self.change_thermostat_mode(entity_id=register.entity_id, mode="auto")
                else:
                    error_msg = f"Climate state should be an integer value of 0, 2, 3, or 4"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            elif entity_point == "temperature":
                self.set_thermostat_temperature(entity_id=register.entity_id, temperature=register.value)

            else:
                error_msg = f"Currently set_point is supported only for thermostats state and temperature {register.entity_id}"
                _log.error(error_msg)
                raise ValueError(error_msg)
        
        # Changing switch values.
        elif "switch." in register.entity_id:
            if entity_point == "state":
                if isinstance(register.value, int) and register.value in [0, 1]:
                    if register.value == 1:
                        self.turn_on_switch(register.entity_id)
                    elif register.value == 0:
                        self.turn_off_switch(register.entity_id)
                else:
                    error_msg = f"State value for {register.entity_id} should be an integer value of 1 or 0"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            else:
                error_msg = f"Unexpected entity_point {entity_point} for switch {register.entity_id}. " \
                            f"Supported: state"
                _log.error(error_msg)
                raise ValueError(error_msg)

        # Changing cover values.
        elif "cover." in register.entity_id:
            if entity_point == "state":
                # State values: 0=closed, 1=open, 2=stop
                if isinstance(register.value, int) and register.value in [0, 1, 2]:
                    if register.value == 0:
                        self.close_cover(register.entity_id)
                    elif register.value == 1:
                        self.open_cover(register.entity_id)
                    elif register.value == 2:
                        self.stop_cover(register.entity_id)
                else:
                    error_msg = f"Cover state should be an integer value of 0 (close), 1 (open), or 2 (stop)"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            elif entity_point == "position" or entity_point == "current_position":
                # Position: 0-100 (0=closed, 100=fully open)
                if isinstance(register.value, (int, float)) and 0 <= register.value <= 100:
                    self.set_cover_position(register.entity_id, register.value)
                else:
                    error_msg = f"Cover position should be a number between 0 and 100, got {register.value}"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            elif entity_point == "tilt_position" or entity_point == "current_tilt_position":
                # Tilt position: 0-100
                if isinstance(register.value, (int, float)) and 0 <= register.value <= 100:
                    self.set_cover_tilt_position(register.entity_id, register.value)
                else:
                    error_msg = f"Cover tilt_position should be a number between 0 and 100, got {register.value}"
                    _log.error(error_msg)
                    raise ValueError(error_msg)
            else:
                error_msg = f"Unsupported entity_point '{entity_point}' for cover {register.entity_id}. " \
                            f"Supported points: state, position, current_position, tilt_position, current_tilt_position"
                _log.error(error_msg)
                raise ValueError(error_msg)
        else:
            error_msg = f"Unsupported entity_id: {register.entity_id}. " \
                        f"Currently set_point is supported only for thermostats, lights, input_booleans, and fans"
            _log.error(error_msg)
            raise ValueError(error_msg)
        return register.value

    def get_entity_data(self, point_name):
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        # the /states grabs current state AND attributes of a specific entity
        url = f"http://{self.ip_address}:{self.port}/api/states/{point_name}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()  # return the json attributes from entity
        else:
            error_msg = f"Request failed with status code {response.status_code}, Point name: {point_name}, " \
                        f"response: {response.text}"
            _log.error(error_msg)
            raise Exception(error_msg)

    def _scrape_all(self):
        result = {}
        read_registers = self.get_registers_by_type("byte", True)
        write_registers = self.get_registers_by_type("byte", False)

        for register in read_registers + write_registers:
            entity_id = register.entity_id
            entity_point = register.entity_point
            try:
                entity_data = self.get_entity_data(entity_id)  # Using Entity ID to get data
                if "climate." in entity_id:  # handling thermostats.
                    if entity_point == "state":
                        state = entity_data.get("state", None)
                        # Giving thermostat states an equivalent number.
                        if state == "off":
                            register.value = 0
                            result[register.point_name] = 0
                        elif state == "heat":
                            register.value = 2
                            result[register.point_name] = 2
                        elif state == "cool":
                            register.value = 3
                            result[register.point_name] = 3
                        elif state == "auto":
                            register.value = 4
                            result[register.point_name] = 4
                        else:
                            error_msg = f"State {state} from {entity_id} is not yet supported"
                            _log.error(error_msg)
                            ValueError(error_msg)
                    # Assigning attributes
                    else:
                        attribute = entity_data.get("attributes", {}).get(f"{entity_point}", 0)
                        register.value = attribute
                        result[register.point_name] = attribute
                # handling fan states
                elif "fan." in entity_id:
                    if entity_point == "state":
                        state = entity_data.get("state", None)
                        # Converting fan states to numbers (on=1, off=0).
                        if state == "on":
                            register.value = 1
                            result[register.point_name] = 1
                        elif state == "off":
                            register.value = 0
                            result[register.point_name] = 0
                        else:
                            register.value = state
                            result[register.point_name] = state
                    elif entity_point == "oscillating":
                        # Convert boolean to int for consistency
                        oscillating = entity_data.get("attributes", {}).get("oscillating", False)
                        register.value = 1 if oscillating else 0
                        result[register.point_name] = register.value
                    else:
                        # Handle percentage, preset_mode, direction, and other attributes
                        attribute = entity_data.get("attributes", {}).get(f"{entity_point}", None)
                        register.value = attribute
                        result[register.point_name] = attribute
                # handling switch states
                elif "switch." in entity_id:
                    if entity_point == "state":
                        state = entity_data.get("state", None)
                        # Converting switch states to numbers (on=1, off=0).
                        if state == "on":
                            register.value = 1
                            result[register.point_name] = 1
                        elif state == "off":
                            register.value = 0
                            result[register.point_name] = 0
                        else:
                            register.value = state
                            result[register.point_name] = state
                    else:
                        # Handle other switch attributes
                        attribute = entity_data.get("attributes", {}).get(f"{entity_point}", None)
                        register.value = attribute
                        result[register.point_name] = attribute
                # handling cover states
                elif "cover." in entity_id:
                    if entity_point == "state":
                        state = entity_data.get("state", None)
                        # Converting cover states to numbers: closed=0, open=1, opening=1, closing=0
                        if state in ["open", "opening"]:
                            register.value = 1
                            result[register.point_name] = 1
                        elif state in ["closed", "closing"]:
                            register.value = 0
                            result[register.point_name] = 0
                        else:
                            # Handle unknown state
                            _log.warning(f"Unknown cover state '{state}' for {entity_id}, defaulting to 0")
                            register.value = 0
                            result[register.point_name] = 0
                    else:
                        # Handling position, tilt_position, and other attributes
                        attribute = entity_data.get("attributes", {}).get(f"{entity_point}", 0)
                        register.value = attribute
                        result[register.point_name] = attribute
                # handling light states
                elif "light." in entity_id or "input_boolean." in entity_id:  # Checks for lights or input bools since they have the same states.
                    if entity_point == "state":
                        state = entity_data.get("state", None)
                        # Converting light states to numbers.
                        if state == "on":
                            register.value = 1
                            result[register.point_name] = 1
                        elif state == "off":
                            register.value = 0
                            result[register.point_name] = 0
                    else:
                        attribute = entity_data.get("attributes", {}).get(f"{entity_point}", 0)
                        register.value = attribute
                        result[register.point_name] = attribute
                else:  # handling all devices that are not thermostats, fans, or light states
                    if entity_point == "state":

                        state = entity_data.get("state", None)
                        register.value = state
                        result[register.point_name] = state
                    # Assigning attributes
                    else:
                        attribute = entity_data.get("attributes", {}).get(f"{entity_point}", 0)
                        register.value = attribute
                        result[register.point_name] = attribute
            except Exception as e:
                _log.error(f"An unexpected error occurred for entity_id: {entity_id}: {e}")

        return result

    def parse_config(self, config_dict):

        if config_dict is None:
            return
        for regDef in config_dict:

            if not regDef['Entity ID']:
                continue

            read_only = str(regDef.get('Writable', '')).lower() != 'true'
            entity_id = regDef['Entity ID']
            entity_point = regDef['Entity Point']
            self.point_name = regDef['Volttron Point Name']
            self.units = regDef['Units']
            description = regDef.get('Notes', '')
            default_value = ("Starting Value")
            type_name = regDef.get("Type", 'string')
            reg_type = type_mapping.get(type_name, str)
            attributes = regDef.get('Attributes', {})
            register_type = HomeAssistantRegister

            register = register_type(
                read_only,
                self.point_name,
                self.units,
                reg_type,
                attributes,
                entity_id,
                entity_point,
                default_value=default_value,
                description=description)

            if default_value is not None:
                self.set_default(self.point_name, register.value)

            self.insert_register(register)

    def turn_off_lights(self, entity_id):
        url = f"http://{self.ip_address}:{self.port}/api/services/light/turn_off"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id,
        }
        _post_method(url, headers, payload, f"turn off {entity_id}")

    def turn_on_lights(self, entity_id):
        url = f"http://{self.ip_address}:{self.port}/api/services/light/turn_on"
        headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
        }

        payload = {
            "entity_id": f"{entity_id}"
        }
        _post_method(url, headers, payload, f"turn on {entity_id}")

    def change_thermostat_mode(self, entity_id, mode):
        # Check if enttiy_id startswith climate.
        if not entity_id.startswith("climate."):
            _log.error(f"{entity_id} is not a valid thermostat entity ID.")
            return
        # Build header
        url = f"http://{self.ip_address}:{self.port}/api/services/climate/set_hvac_mode"
        headers = {
                "Authorization": f"Bearer {self.access_token}",
                "content-type": "application/json",
        }
        # Build data
        data = {
            "entity_id": entity_id,
            "hvac_mode": mode,
        }
        # Post data
        _post_method(url, headers, data, f"change mode of {entity_id} to {mode}")

    def set_thermostat_temperature(self, entity_id, temperature):
        # Check if the provided entity_id starts with "climate."
        if not entity_id.startswith("climate."):
            _log.error(f"{entity_id} is not a valid thermostat entity ID.")
            return

        url = f"http://{self.ip_address}:{self.port}/api/services/climate/set_temperature"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "content-type": "application/json",
        }

        if self.units == "C":
            converted_temp = round((temperature - 32) * 5/9, 1)
            _log.info(f"Converted temperature {converted_temp}")
            data = {
                "entity_id": entity_id,
                "temperature": converted_temp,
            }
        else:
            data = {
                "entity_id": entity_id,
                "temperature": temperature,
            }
        _post_method(url, headers, data, f"set temperature of {entity_id} to {temperature}")

    def change_brightness(self, entity_id, value):
        url = f"http://{self.ip_address}:{self.port}/api/services/light/turn_on"
        headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
        }
        # ranges from 0 - 255
        payload = {
            "entity_id": f"{entity_id}",
            "brightness": value,
        }

        _post_method(url, headers, payload, f"set brightness of {entity_id} to {value}")

    def set_input_boolean(self, entity_id, state):
        service = 'turn_on' if state == 'on' else 'turn_off'
        url = f"http://{self.ip_address}:{self.port}/api/services/input_boolean/{service}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "entity_id": entity_id
        }

        response = requests.post(url, headers=headers, json=payload)

        # Optionally check for a successful response
        if response.status_code == 200:
            print(f"Successfully set {entity_id} to {state}")
        else:
            print(f"Failed to set {entity_id} to {state}: {response.text}")

    # Fan control methods
    # Reference: https://www.home-assistant.io/integrations/fan/
    # API: https://developers.home-assistant.io/docs/api/rest/

    def turn_on_fan(self, entity_id, percentage=None, preset_mode=None):
        """Turn on a fan device with optional percentage or preset_mode."""
        url = f"http://{self.ip_address}:{self.port}/api/services/fan/turn_on"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id
        }
        if percentage is not None:
            payload["percentage"] = percentage
        if preset_mode is not None:
            payload["preset_mode"] = preset_mode

        _post_method(url, headers, payload, f"turn on fan {entity_id}")

    def turn_off_fan(self, entity_id):
        """Turn off a fan device."""
        url = f"http://{self.ip_address}:{self.port}/api/services/fan/turn_off"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id
        }
        _post_method(url, headers, payload, f"turn off fan {entity_id}")

    def set_fan_percentage(self, entity_id, percentage):
        """Set the speed percentage for a fan device (0-100)."""
        if not entity_id.startswith("fan."):
            error_msg = f"{entity_id} is not a valid fan entity ID."
            _log.error(error_msg)
            raise ValueError(error_msg)

        url = f"http://{self.ip_address}:{self.port}/api/services/fan/set_percentage"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id,
            "percentage": percentage
        }
        _post_method(url, headers, payload, f"set fan {entity_id} percentage to {percentage}")

    def set_fan_preset_mode(self, entity_id, preset_mode):
        """Set a preset mode for a fan device (e.g., 'Low', 'Medium', 'High', 'auto')."""
        if not entity_id.startswith("fan."):
            error_msg = f"{entity_id} is not a valid fan entity ID."
            _log.error(error_msg)
            raise ValueError(error_msg)

        url = f"http://{self.ip_address}:{self.port}/api/services/fan/set_preset_mode"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id,
            "preset_mode": preset_mode
        }
        _post_method(url, headers, payload, f"set fan {entity_id} preset mode to {preset_mode}")

    def set_fan_direction(self, entity_id, direction):
        """Set the rotation direction for a fan device ('forward' or 'reverse')."""
        if not entity_id.startswith("fan."):
            error_msg = f"{entity_id} is not a valid fan entity ID."
            _log.error(error_msg)
            raise ValueError(error_msg)

        if direction not in ["forward", "reverse"]:
            error_msg = f"Invalid direction '{direction}'. Must be 'forward' or 'reverse'."
            _log.error(error_msg)
            raise ValueError(error_msg)

        url = f"http://{self.ip_address}:{self.port}/api/services/fan/set_direction"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id,
            "direction": direction
        }
        _post_method(url, headers, payload, f"set fan {entity_id} direction to {direction}")

    def set_fan_oscillation(self, entity_id, oscillating):
        """Set the oscillation for a fan device (True or False)."""
        if not entity_id.startswith("fan."):
            error_msg = f"{entity_id} is not a valid fan entity ID."
            _log.error(error_msg)
            raise ValueError(error_msg)

        url = f"http://{self.ip_address}:{self.port}/api/services/fan/oscillate"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id,
            "oscillating": oscillating
        }
        _post_method(url, headers, payload, f"set fan {entity_id} oscillating to {oscillating}")

    # Switch control methods
    # Reference: https://www.home-assistant.io/integrations/switch/
    # API: https://developers.home-assistant.io/docs/api/rest/

    def turn_on_switch(self, entity_id):
        """Turn on a switch device."""
        if not entity_id.startswith("switch."):
            error_msg = f"{entity_id} is not a valid switch entity ID."
            _log.error(error_msg)
            raise ValueError(error_msg)

        url = f"http://{self.ip_address}:{self.port}/api/services/switch/turn_on"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id
        }
        _post_method(url, headers, payload, f"turn on switch {entity_id}")

    def turn_off_switch(self, entity_id):
        """Turn off a switch device."""
        if not entity_id.startswith("switch."):
            error_msg = f"{entity_id} is not a valid switch entity ID."
            _log.error(error_msg)
            raise ValueError(error_msg)

        url = f"http://{self.ip_address}:{self.port}/api/services/switch/turn_off"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id
        }
        _post_method(url, headers, payload, f"turn off switch {entity_id}")

    # Cover control methods
    # Reference: https://www.home-assistant.io/integrations/cover/
    # API: https://developers.home-assistant.io/docs/core/entity/cover/

    def open_cover(self, entity_id):
        """Open a cover device."""
        if not entity_id.startswith("cover."):
            error_msg = f"{entity_id} is not a valid cover entity ID."
            _log.error(error_msg)
            raise ValueError(error_msg)

        url = f"http://{self.ip_address}:{self.port}/api/services/cover/open_cover"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id
        }
        _post_method(url, headers, payload, f"open cover {entity_id}")

    def close_cover(self, entity_id):
        """Close a cover device."""
        if not entity_id.startswith("cover."):
            error_msg = f"{entity_id} is not a valid cover entity ID."
            _log.error(error_msg)
            raise ValueError(error_msg)

        url = f"http://{self.ip_address}:{self.port}/api/services/cover/close_cover"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id
        }
        _post_method(url, headers, payload, f"close cover {entity_id}")

    def stop_cover(self, entity_id):
        """Stop a cover device."""
        if not entity_id.startswith("cover."):
            error_msg = f"{entity_id} is not a valid cover entity ID."
            _log.error(error_msg)
            raise ValueError(error_msg)

        url = f"http://{self.ip_address}:{self.port}/api/services/cover/stop_cover"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id
        }
        _post_method(url, headers, payload, f"stop cover {entity_id}")

    def set_cover_position(self, entity_id, position):
        """Set the position of a cover device (0-100, where 0=closed and 100=fully open)."""
        if not entity_id.startswith("cover."):
            error_msg = f"{entity_id} is not a valid cover entity ID."
            _log.error(error_msg)
            raise ValueError(error_msg)

        if not isinstance(position, (int, float)) or not 0 <= position <= 100:
            error_msg = f"Position must be a number between 0 and 100, got {position}"
            _log.error(error_msg)
            raise ValueError(error_msg)

        url = f"http://{self.ip_address}:{self.port}/api/services/cover/set_cover_position"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id,
            "position": int(position)
        }
        _post_method(url, headers, payload, f"set position of {entity_id} to {position}")

    def set_cover_tilt_position(self, entity_id, tilt_position):
        """Set the tilt position of a cover device (0-100)."""
        if not entity_id.startswith("cover."):
            error_msg = f"{entity_id} is not a valid cover entity ID."
            _log.error(error_msg)
            raise ValueError(error_msg)

        if not isinstance(tilt_position, (int, float)) or not 0 <= tilt_position <= 100:
            error_msg = f"Tilt position must be a number between 0 and 100, got {tilt_position}"
            _log.error(error_msg)
            raise ValueError(error_msg)

        url = f"http://{self.ip_address}:{self.port}/api/services/cover/set_cover_tilt_position"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id,
            "tilt_position": int(tilt_position)
        }
        _post_method(url, headers, payload, f"set tilt position of {entity_id} to {tilt_position}")