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

"""
Home Assistant Interface for VOLTTRON Platform Driver

This module provides a driver interface for integrating Home Assistant devices
with the VOLTTRON platform. It supports reading and writing to various Home 
Assistant entity types including lights, thermostats, fans, switches, covers, 
and input_booleans.

Architecture:
-------------
Uses Strategy Pattern with dictionary-based dispatch for handling different device types.
Each device type has dedicated read/write handler methods for improved maintainability.

Adding New Device Types:
------------------------
1. Create write handler: _handle_DEVICE_write(self, register, entity_point)
2. Create scrape handler: _scrape_DEVICE(self, register, entity_point, entity_data, result)
3. Register both in __init__ dictionaries
4. Add API methods for Home Assistant calls
"""

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

# Type mapping for registry configuration
type_mapping = {"string": str,
                "int": int,
                "integer": int,
                "float": float,
                "bool": bool,
                "boolean": bool}


class HomeAssistantRegister(BaseRegister):
    """
    Register for Home Assistant entities.
    
    Extends BaseRegister to include Home Assistant-specific attributes:
    - entity_id: The Home Assistant entity identifier (e.g., 'light.living_room')
    - entity_point: The specific point being controlled (e.g., 'state', 'brightness')
    - reg_type: The expected data type for this register
    """
    def __init__(self, read_only, pointName, units, reg_type, attributes, entity_id, entity_point, default_value=None,
                 description=''):
        super(HomeAssistantRegister, self).__init__("byte", read_only, pointName, units, description='')
        self.reg_type = reg_type
        self.attributes = attributes
        self.entity_id = entity_id
        self.value = None
        self.entity_point = entity_point


def _post_method(url, headers, data, operation_description):
    """
    Centralized POST request handler for Home Assistant API calls.
    
    Provides consistent error handling and logging for all API operations.
    
    Args:
        url: The API endpoint URL
        headers: HTTP headers including authorization
        data: JSON payload to send
        operation_description: Human-readable description for logging
        
    Raises:
        Exception: If the API call fails
    """
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
    """
    Home Assistant interface for VOLTTRON Platform Driver.
    
    This class implements the bridge between VOLTTRON and Home Assistant,
    handling both read (scrape) and write (set_point) operations for multiple
    device types.
    
    Design Pattern: Strategy Pattern
    --------------------------------
    Different device types are handled by separate handler methods that are
    registered in dictionaries. This makes the code:
    - Easy to extend with new device types
    - Easy to test (each handler can be tested independently)
    - Easy to maintain (device-specific logic is isolated)
    
    Supported Devices:
    -----------------
    - Lights (state, brightness)
    - Thermostats (state/mode, temperature)
    - Fans (state, percentage, preset_mode, direction, oscillating)
    - Switches (state)
    - Covers (state, position, tilt_position)
    - Input Booleans (state)
    """
    
    def __init__(self, **kwargs):
        super(Interface, self).__init__(**kwargs)
        
        # Configuration properties
        self.point_name = None
        self.ip_address = None
        self.access_token = None
        self.port = None
        self.units = None
        
        # ====================================================================
        # HANDLER REGISTRATION (Strategy Pattern)
        # ====================================================================
        # These dictionaries map entity type prefixes to their handler methods.
        # To add a new device type, simply add an entry here and implement
        # the corresponding handler method below.
        
        # Write operation handlers: route set_point calls to device-specific logic
        self._write_handlers = {
            "light.": self._handle_light_write,
            "input_boolean.": self._handle_input_boolean_write,
            "fan.": self._handle_fan_write,
            "climate.": self._handle_thermostat_write,  # climate = thermostat in Home Assistant
            "switch.": self._handle_switch_write,
            "cover.": self._handle_cover_write,
        }
        
        # Read operation handlers: route scrape calls to device-specific logic
        self._scrape_handlers = {
            "climate.": self._scrape_thermostat,
            "fan.": self._scrape_fan,
            "switch.": self._scrape_switch,
            "cover.": self._scrape_cover,
            "light.": self._scrape_light_or_input_boolean,
            "input_boolean.": self._scrape_light_or_input_boolean,
        }

    def configure(self, config_dict, registry_config_str):
        """
        Configure the interface with connection details and register definitions.
        
        Args:
            config_dict: Dictionary containing ip_address, access_token, and port
            registry_config_str: Registry configuration defining the points to monitor
        """
        # Extract connection configuration
        self.ip_address = config_dict.get("ip_address", None)
        self.access_token = config_dict.get("access_token", None)
        self.port = config_dict.get("port", None)

        # Validate required configuration (Fail-fast principle)
        if self.ip_address is None:
            _log.error("IP address is not set.")
            raise ValueError("IP address is required.")
        if self.access_token is None:
            _log.error("Access token is not set.")
            raise ValueError("Access token is required.")
        if self.port is None:
            _log.error("Port is not set.")
            raise ValueError("Port is required.")

        # Parse and create registers from configuration
        self.parse_config(registry_config_str)

    def get_point(self, point_name):
        """
        Read a single point value from Home Assistant.
        
        Args:
            point_name: The VOLTTRON point name to read
            
        Returns:
            The current value of the point
        """
        register = self.get_register_by_name(point_name)
        entity_data = self.get_entity_data(register.entity_id)
        
        # Handle state vs. attribute reads
        if register.point_name == "state":
            result = entity_data.get("state", None)
            return result
        else:
            value = entity_data.get("attributes", {}).get(f"{register.point_name}", 0)
            return value

    # ========================================================================
    # WRITE OPERATION ROUTING (Strategy Pattern Entry Point)
    # ========================================================================
    
    def _set_point(self, point_name, value):
        """
        Set a point value in Home Assistant.
        
        This is the main entry point for write operations. It:
        1. Validates the point is writable
        2. Converts the value to the correct type
        3. Routes to the appropriate device handler based on entity_id prefix
        
        Design Note: This method follows the Open/Closed Principle - it's open
        for extension (add new handlers) but closed for modification (no need
        to change this method when adding new device types).
        
        Args:
            point_name: The VOLTTRON point name to write
            value: The value to write
            
        Returns:
            The value that was written
            
        Raises:
            IOError: If the point is read-only
            ValueError: If the entity type is not supported
        """
        # Get the register and validate it's writable
        register = self.get_register_by_name(point_name)
        if register.read_only:
            raise IOError(f"Trying to write to a point configured read only: {point_name}")
        
        # Convert value to the expected type
        register.value = register.reg_type(value)
        entity_point = register.entity_point
        
        # Find the appropriate handler using Strategy Pattern (O(1) lookup)
        handler = self._get_entity_handler(register.entity_id, self._write_handlers)
        
        if handler:
            # Delegate to device-specific handler
            return handler(register, entity_point)
        
        # No handler found - entity type not supported
        error_msg = (
            f"Unsupported entity_id: {register.entity_id}. "
            f"Supported types: {', '.join(self._write_handlers.keys())}"
        )
        _log.error(error_msg)
        raise ValueError(error_msg)

    def _get_entity_handler(self, entity_id, handler_dict):
        """
        Get the appropriate handler for an entity based on its type prefix.
        
        This is a key routing method that enables the Strategy Pattern.
        It matches entity IDs like 'light.living_room' to handlers registered
        for the 'light.' prefix.
        
        Args:
            entity_id: The Home Assistant entity ID (e.g., 'light.living_room')
            handler_dict: Dictionary mapping prefixes to handler methods
            
        Returns:
            The handler method, or None if no match found
        """
        for prefix, handler in handler_dict.items():
            if entity_id.startswith(prefix):
                return handler
        return None

    # ========================================================================
    # VALIDATION HELPERS (DRY Principle)
    # ========================================================================
    # These methods extract common validation patterns to avoid code duplication.
    # Each provides consistent error messages and type checking.
    
    def _validate_binary_state(self, register, allowed_values=(0, 1)):
        """
        Validate that a value is one of the allowed integer states.
        
        Common pattern for on/off controls where 0=off, 1=on.
        
        Args:
            register: The register containing the value to validate
            allowed_values: Tuple of allowed integer values
            
        Returns:
            The validated value
            
        Raises:
            ValueError: If validation fails
        """
        if not isinstance(register.value, int) or register.value not in allowed_values:
            raise ValueError(
                f"State value for {register.entity_id} should be an integer "
                f"from {allowed_values}, got {register.value}"
            )
        return register.value

    def _validate_range(self, register, min_val, max_val, value_name="value"):
        """
        Validate that a numeric value is within a specified range.
        
        Used for percentage values, brightness levels, etc.
        
        Args:
            register: The register containing the value to validate
            min_val: Minimum allowed value (inclusive)
            max_val: Maximum allowed value (inclusive)
            value_name: Human-readable name for error messages
            
        Returns:
            The validated value
            
        Raises:
            ValueError: If validation fails
        """
        if not isinstance(register.value, (int, float)) or not (min_val <= register.value <= max_val):
            raise ValueError(
                f"{value_name} for {register.entity_id} should be between "
                f"{min_val} and {max_val}, got {register.value}"
            )
        return register.value

    def _validate_string_choice(self, register, choices, value_name="value"):
        """
        Validate that a string value is one of the allowed choices.
        
        Used for enumerated string values like fan direction ('forward'/'reverse').
        
        Args:
            register: The register containing the value to validate
            choices: List of allowed string values
            value_name: Human-readable name for error messages
            
        Returns:
            The validated value
            
        Raises:
            ValueError: If validation fails
        """
        if not isinstance(register.value, str) or register.value not in choices:
            # Format choices as 'choice1' or 'choice2' for better readability
            choices_str = "' or '".join(choices)
            raise ValueError(
                f"{value_name} for {register.entity_id} should be '{choices_str}', "
                f"got '{register.value}'"
            )
        return register.value

    # ========================================================================
    # WRITE HANDLERS (Device-Specific Logic)
    # ========================================================================
    
    def _handle_light_write(self, register, entity_point):
        """
        Handle write operations for light entities.
        
        Supported entity_points:
        - state: Turn light on (1) or off (0)
        - brightness: Set brightness level (0-255)
        """
        if entity_point == "state":
            self._validate_binary_state(register)
            action = self.turn_on_lights if register.value == 1 else self.turn_off_lights
            action(register.entity_id)
            
        elif entity_point == "brightness":
            self._validate_range(register, 0, 255, "Brightness")
            self.change_brightness(register.entity_id, register.value)
            
        else:
            raise ValueError(
                f"Unexpected entity_point '{entity_point}' for light {register.entity_id}. "
                f"Supported: state, brightness"
            )
        return register.value

    def _handle_input_boolean_write(self, register, entity_point):
        """Handle write operations for input_boolean entities (state only)."""
        if entity_point == "state":
            self._validate_binary_state(register)
            state = "on" if register.value == 1 else "off"
            self.set_input_boolean(register.entity_id, state)
        else:
            _log.info(f"Currently, input_booleans only support 'state' entity_point")
        return register.value

    def _handle_fan_write(self, register, entity_point):
        """
        Handle write operations for fan entities.
        
        Uses nested dispatch pattern for multiple controllable attributes.
        
        Supported entity_points:
        - state: Turn fan on (1) or off (0)
        - percentage: Set fan speed (0-100)
        - preset_mode: Set preset mode (string, e.g., 'auto', 'sleep')
        - direction: Set rotation direction ('forward' or 'reverse')
        - oscillating: Enable/disable oscillation (0/1 or True/False)
        """
        # Nested handler dictionary for fan-specific operations
        handlers = {
            "state": lambda: self._handle_fan_state(register),
            "percentage": lambda: self._handle_fan_percentage(register),
            "preset_mode": lambda: self._handle_fan_preset_mode(register),
            "direction": lambda: self._handle_fan_direction(register),
            "oscillating": lambda: self._handle_fan_oscillating(register),
        }
        
        handler = handlers.get(entity_point)
        if handler:
            return handler()
        
        raise ValueError(
            f"Unexpected entity_point '{entity_point}' for fan {register.entity_id}. "
            f"Supported: {', '.join(handlers.keys())}"
        )

    def _handle_fan_state(self, register):
        """Handle fan on/off state changes."""
        self._validate_binary_state(register)
        action = self.turn_on_fan if register.value == 1 else self.turn_off_fan
        action(register.entity_id)
        return register.value

    def _handle_fan_percentage(self, register):
        """Handle fan speed percentage changes (0-100)."""
        self._validate_range(register, 0, 100, "Fan percentage")
        self.set_fan_percentage(register.entity_id, register.value)
        return register.value

    def _handle_fan_preset_mode(self, register):
        """Handle fan preset mode changes (e.g., 'auto', 'sleep')."""
        if not isinstance(register.value, str) or not register.value:
            raise ValueError(f"Fan preset_mode for {register.entity_id} should be a non-empty string")
        self.set_fan_preset_mode(register.entity_id, register.value)
        return register.value

    def _handle_fan_direction(self, register):
        """Handle fan rotation direction changes ('forward' or 'reverse')."""
        self._validate_string_choice(register, ["forward", "reverse"], "Fan direction")
        self.set_fan_direction(register.entity_id, register.value)
        return register.value

    def _handle_fan_oscillating(self, register):
        """Handle fan oscillation changes (accepts both bool and int 0/1)."""
        if isinstance(register.value, bool):
            oscillating = register.value
        elif isinstance(register.value, int) and register.value in [0, 1]:
            oscillating = bool(register.value)
        else:
            raise ValueError(
                f"Fan oscillating value for {register.entity_id} should be "
                f"0, 1, True, or False, got {register.value}"
            )
        self.set_fan_oscillation(register.entity_id, oscillating)
        return register.value

    def _handle_thermostat_write(self, register, entity_point):
        """
        Handle write operations for thermostat (climate) entities.
        
        Supported entity_points:
        - state: Set HVAC mode (0=off, 2=heat, 3=cool, 4=auto)
        - temperature: Set target temperature
        """
        if entity_point == "state":
            self._validate_binary_state(register, allowed_values=(0, 2, 3, 4))
            mode_mapping = {0: "off", 2: "heat", 3: "cool", 4: "auto"}
            self.change_thermostat_mode(
                entity_id=register.entity_id, 
                mode=mode_mapping[register.value]
            )
        elif entity_point == "temperature":
            self.set_thermostat_temperature(
                entity_id=register.entity_id, 
                temperature=register.value
            )
        else:
            raise ValueError(
                f"Unexpected entity_point '{entity_point}' for thermostat {register.entity_id}. "
                f"Supported: state, temperature"
            )
        return register.value

    def _handle_switch_write(self, register, entity_point):
        """Handle write operations for switch entities (state only)."""
        if entity_point == "state":
            self._validate_binary_state(register)
            action = self.turn_on_switch if register.value == 1 else self.turn_off_switch
            action(register.entity_id)
        else:
            raise ValueError(
                f"Unexpected entity_point '{entity_point}' for switch {register.entity_id}. "
                f"Supported: state"
            )
        return register.value

    def _handle_cover_write(self, register, entity_point):
        """
        Handle write operations for cover entities (blinds, shades, garage doors).
        
        Supported entity_points:
        - state: Control cover (0=close, 1=open, 2=stop)
        - position/current_position: Set position (0-100)
        - tilt_position/current_tilt_position: Set tilt angle (0-100)
        """
        if entity_point == "state":
            self._validate_binary_state(register, allowed_values=(0, 1, 2))
            actions = {0: self.close_cover, 1: self.open_cover, 2: self.stop_cover}
            actions[register.value](register.entity_id)
            
        elif entity_point in ["position", "current_position"]:
            self._validate_range(register, 0, 100, "Cover position")
            self.set_cover_position(register.entity_id, register.value)
            
        elif entity_point in ["tilt_position", "current_tilt_position"]:
            self._validate_range(register, 0, 100, "Cover tilt position")
            self.set_cover_tilt_position(register.entity_id, register.value)
            
        else:
            raise ValueError(
                f"Unsupported entity_point '{entity_point}' for cover {register.entity_id}. "
                f"Supported: state, position, current_position, tilt_position, current_tilt_position"
            )
        return register.value

    # ========================================================================
    # READ OPERATIONS (Scraping)
    # ========================================================================
    
    def get_entity_data(self, entity_id):
        """Fetch current state and attributes for an entity from Home Assistant."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        url = f"http://{self.ip_address}:{self.port}/api/states/{entity_id}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            error_msg = (
                f"Failed to get entity data for {entity_id}. "
                f"Status: {getattr(response, 'status_code', 'N/A')}, Error: {e}"
            )
            _log.error(error_msg)
            raise Exception(error_msg)

    def _scrape_all(self):
        """Read all register values from Home Assistant (scrape operation)."""
        result = {}
        read_registers = self.get_registers_by_type("byte", True)
        write_registers = self.get_registers_by_type("byte", False)

        for register in read_registers + write_registers:
            entity_id = register.entity_id
            entity_point = register.entity_point
            try:
                entity_data = self.get_entity_data(entity_id)
                self._scrape_entity(register, entity_point, entity_data, result)
            except Exception as e:
                _log.error(f"Error scraping entity {entity_id}: {e}")

        return result

    def _scrape_entity(self, register, entity_point, entity_data, result):
        """Route entity scrape to appropriate handler based on entity type."""
        handler = self._get_entity_handler(register.entity_id, self._scrape_handlers)
        
        if handler:
            handler(register, entity_point, entity_data, result)
        else:
            # Fallback for unknown entity types
            self._scrape_generic(register, entity_point, entity_data, result)

    def _scrape_generic(self, register, entity_point, entity_data, result):
        """Generic scraper for unknown entity types - reads state or attributes directly."""
        if entity_point == "state":
            state = entity_data.get("state", None)
            register.value = state
            result[register.point_name] = state
        else:
            attribute = entity_data.get("attributes", {}).get(entity_point, 0)
            register.value = attribute
            result[register.point_name] = attribute

    # ========================================================================
    # READ HANDLERS (Device-Specific Scraping)
    # ========================================================================
    
    def _scrape_thermostat(self, register, entity_point, entity_data, result):
        """
        Scrape thermostat state and attributes.
        Transforms HVAC modes to numeric codes: off=0, heat=2, cool=3, auto=4
        """
        if entity_point == "state":
            state = entity_data.get("state", None)
            state_mapping = {"off": 0, "heat": 2, "cool": 3, "auto": 4}
            
            if state in state_mapping:
                register.value = state_mapping[state]
                result[register.point_name] = state_mapping[state]
            else:
                _log.warning(f"Unsupported thermostat state '{state}' for {register.entity_id}")
                register.value = None
                result[register.point_name] = None
        else:
            attribute = entity_data.get("attributes", {}).get(entity_point, 0)
            register.value = attribute
            result[register.point_name] = attribute

    def _scrape_fan(self, register, entity_point, entity_data, result):
        """Scrape fan state and attributes (converts on/off to 1/0)."""
        if entity_point == "state":
            state = entity_data.get("state", None)
            state_value = 1 if state == "on" else 0 if state == "off" else state
            register.value = state_value
            result[register.point_name] = state_value
            
        elif entity_point == "oscillating":
            oscillating = entity_data.get("attributes", {}).get("oscillating", False)
            register.value = 1 if oscillating else 0
            result[register.point_name] = register.value
            
        else:
            attribute = entity_data.get("attributes", {}).get(entity_point, None)
            register.value = attribute
            result[register.point_name] = attribute

    def _scrape_switch(self, register, entity_point, entity_data, result):
        """Scrape switch state and attributes (converts on/off to 1/0)."""
        if entity_point == "state":
            state = entity_data.get("state", None)
            state_value = 1 if state == "on" else 0 if state == "off" else state
            register.value = state_value
            result[register.point_name] = state_value
        else:
            attribute = entity_data.get("attributes", {}).get(entity_point, None)
            register.value = attribute
            result[register.point_name] = attribute

    def _scrape_cover(self, register, entity_point, entity_data, result):
        """Scrape cover state and attributes (open/opening=1, closed/closing=0)."""
        if entity_point == "state":
            state = entity_data.get("state", None)
            if state in ["open", "opening"]:
                state_value = 1
            elif state in ["closed", "closing"]:
                state_value = 0
            else:
                _log.warning(f"Unknown cover state '{state}' for {register.entity_id}, defaulting to 0")
                state_value = 0
            
            register.value = state_value
            result[register.point_name] = state_value
        else:
            attribute = entity_data.get("attributes", {}).get(entity_point, 0)
            register.value = attribute
            result[register.point_name] = attribute

    def _scrape_light_or_input_boolean(self, register, entity_point, entity_data, result):
        """Scrape light/input_boolean state and attributes (converts on/off to 1/0)."""
        if entity_point == "state":
            state = entity_data.get("state", None)
            state_value = 1 if state == "on" else 0 if state == "off" else None
            register.value = state_value
            result[register.point_name] = state_value
        else:
            attribute = entity_data.get("attributes", {}).get(entity_point, 0)
            register.value = attribute
            result[register.point_name] = attribute

    # ========================================================================
    # CONFIGURATION PARSING
    # ========================================================================
    
    def parse_config(self, config_dict):
        """Parse registry configuration and create registers."""
        if config_dict is None:
            return
            
        for regDef in config_dict:
            if not regDef.get('Entity ID'):
                continue

            read_only = str(regDef.get('Writable', '')).lower() != 'true'
            entity_id = regDef['Entity ID']
            entity_point = regDef['Entity Point']
            self.point_name = regDef['Volttron Point Name']
            self.units = regDef['Units']
            description = regDef.get('Notes', '')
            default_value = "Starting Value"
            type_name = regDef.get("Type", 'string')
            reg_type = type_mapping.get(type_name, str)
            attributes = regDef.get('Attributes', {})

            register = HomeAssistantRegister(
                read_only,
                self.point_name,
                self.units,
                reg_type,
                attributes,
                entity_id,
                entity_point,
                default_value=default_value,
                description=description
            )

            if default_value is not None:
                self.set_default(self.point_name, register.value)

            self.insert_register(register)

    # ========================================================================
    # HOME ASSISTANT API METHODS - LIGHTS
    # ========================================================================
    
    def turn_off_lights(self, entity_id):
        """Turn off a light entity."""
        url = f"http://{self.ip_address}:{self.port}/api/services/light/turn_off"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"turn off {entity_id}")

    def turn_on_lights(self, entity_id):
        """Turn on a light entity."""
        url = f"http://{self.ip_address}:{self.port}/api/services/light/turn_on"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"turn on {entity_id}")

    def change_brightness(self, entity_id, value):
        """Change the brightness of a light entity (0-255)."""
        url = f"http://{self.ip_address}:{self.port}/api/services/light/turn_on"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "entity_id": entity_id,
            "brightness": value,
        }
        _post_method(url, headers, payload, f"set brightness of {entity_id} to {value}")

    # ========================================================================
    # HOME ASSISTANT API METHODS - THERMOSTATS
    # ========================================================================
    
    def change_thermostat_mode(self, entity_id, mode):
        """Change the HVAC mode of a thermostat (off, heat, cool, auto)."""
        if not entity_id.startswith("climate."):
            raise ValueError(f"{entity_id} is not a valid thermostat entity ID.")

        url = f"http://{self.ip_address}:{self.port}/api/services/climate/set_hvac_mode"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "content-type": "application/json",
        }
        data = {
            "entity_id": entity_id,
            "hvac_mode": mode,
        }
        _post_method(url, headers, data, f"change mode of {entity_id} to {mode}")

    def set_thermostat_temperature(self, entity_id, temperature):
        """Set the target temperature of a thermostat."""
        if not entity_id.startswith("climate."):
            raise ValueError(f"{entity_id} is not a valid thermostat entity ID.")

        url = f"http://{self.ip_address}:{self.port}/api/services/climate/set_temperature"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "content-type": "application/json",
        }

        # Convert temperature if units are Celsius
        if self.units == "C":
            converted_temp = round((temperature - 32) * 5/9, 1)
            _log.info(f"Converted temperature from {temperature}°F to {converted_temp}°C")
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

    # ========================================================================
    # HOME ASSISTANT API METHODS - INPUT BOOLEANS
    # ========================================================================
    
    def set_input_boolean(self, entity_id, state):
        """Set the state of an input_boolean entity (on/off)."""
        service = 'turn_on' if state == 'on' else 'turn_off'
        url = f"http://{self.ip_address}:{self.port}/api/services/input_boolean/{service}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print(f"Successfully set {entity_id} to {state}")
        else:
            print(f"Failed to set {entity_id} to {state}: {response.text}")

    # ========================================================================
    # HOME ASSISTANT API METHODS - FANS
    # ========================================================================
    
    def turn_on_fan(self, entity_id, percentage=None, preset_mode=None):
        """Turn on a fan device with optional percentage or preset_mode."""
        url = f"http://{self.ip_address}:{self.port}/api/services/fan/turn_on"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
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
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"turn off fan {entity_id}")

    def set_fan_percentage(self, entity_id, percentage):
        """Set the speed percentage for a fan device (0-100)."""
        if not entity_id.startswith("fan."):
            raise ValueError(f"{entity_id} is not a valid fan entity ID.")

        url = f"http://{self.ip_address}:{self.port}/api/services/fan/set_percentage"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id, "percentage": percentage}
        _post_method(url, headers, payload, f"set fan {entity_id} percentage to {percentage}")

    def set_fan_preset_mode(self, entity_id, preset_mode):
        """Set a preset mode for a fan device."""
        if not entity_id.startswith("fan."):
            raise ValueError(f"{entity_id} is not a valid fan entity ID.")

        url = f"http://{self.ip_address}:{self.port}/api/services/fan/set_preset_mode"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id, "preset_mode": preset_mode}
        _post_method(url, headers, payload, f"set fan {entity_id} preset mode to {preset_mode}")

    def set_fan_direction(self, entity_id, direction):
        """Set the rotation direction for a fan device ('forward' or 'reverse')."""
        if not entity_id.startswith("fan."):
            raise ValueError(f"{entity_id} is not a valid fan entity ID.")
        if direction not in ["forward", "reverse"]:
            raise ValueError(f"Invalid direction '{direction}'. Must be 'forward' or 'reverse'.")

        url = f"http://{self.ip_address}:{self.port}/api/services/fan/set_direction"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id, "direction": direction}
        _post_method(url, headers, payload, f"set fan {entity_id} direction to {direction}")

    def set_fan_oscillation(self, entity_id, oscillating):
        """Set the oscillation for a fan device (True or False)."""
        if not entity_id.startswith("fan."):
            raise ValueError(f"{entity_id} is not a valid fan entity ID.")

        url = f"http://{self.ip_address}:{self.port}/api/services/fan/oscillate"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id, "oscillating": oscillating}
        _post_method(url, headers, payload, f"set fan {entity_id} oscillating to {oscillating}")

    # ========================================================================
    # HOME ASSISTANT API METHODS - SWITCHES
    # ========================================================================
    
    def turn_on_switch(self, entity_id):
        """Turn on a switch device."""
        if not entity_id.startswith("switch."):
            raise ValueError(f"{entity_id} is not a valid switch entity ID.")

        url = f"http://{self.ip_address}:{self.port}/api/services/switch/turn_on"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"turn on switch {entity_id}")

    def turn_off_switch(self, entity_id):
        """Turn off a switch device."""
        if not entity_id.startswith("switch."):
            raise ValueError(f"{entity_id} is not a valid switch entity ID.")

        url = f"http://{self.ip_address}:{self.port}/api/services/switch/turn_off"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"turn off switch {entity_id}")

    # ========================================================================
    # HOME ASSISTANT API METHODS - COVERS
    # ========================================================================
    
    def open_cover(self, entity_id):
        """Open a cover device (blinds, garage door, etc.)."""
        if not entity_id.startswith("cover."):
            raise ValueError(f"{entity_id} is not a valid cover entity ID.")

        url = f"http://{self.ip_address}:{self.port}/api/services/cover/open_cover"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"open cover {entity_id}")

    def close_cover(self, entity_id):
        """Close a cover device."""
        if not entity_id.startswith("cover."):
            raise ValueError(f"{entity_id} is not a valid cover entity ID.")

        url = f"http://{self.ip_address}:{self.port}/api/services/cover/close_cover"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"close cover {entity_id}")

    def stop_cover(self, entity_id):
        """Stop a moving cover device."""
        if not entity_id.startswith("cover."):
            raise ValueError(f"{entity_id} is not a valid cover entity ID.")

        url = f"http://{self.ip_address}:{self.port}/api/services/cover/stop_cover"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id}
        _post_method(url, headers, payload, f"stop cover {entity_id}")

    def set_cover_position(self, entity_id, position):
        """Set the position of a cover device (0=fully closed, 100=fully open)."""
        if not entity_id.startswith("cover."):
            raise ValueError(f"{entity_id} is not a valid cover entity ID.")
        if not isinstance(position, (int, float)) or not 0 <= position <= 100:
            raise ValueError(f"Position must be between 0 and 100, got {position}")

        url = f"http://{self.ip_address}:{self.port}/api/services/cover/set_cover_position"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id, "position": int(position)}
        _post_method(url, headers, payload, f"set position of {entity_id} to {position}")

    def set_cover_tilt_position(self, entity_id, tilt_position):
        """Set the tilt position of a cover device (0-100)."""
        if not entity_id.startswith("cover."):
            raise ValueError(f"{entity_id} is not a valid cover entity ID.")
        if not isinstance(tilt_position, (int, float)) or not 0 <= tilt_position <= 100:
            raise ValueError(f"Tilt position must be between 0 and 100, got {tilt_position}")

        url = f"http://{self.ip_address}:{self.port}/api/services/cover/set_cover_tilt_position"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"entity_id": entity_id, "tilt_position": int(tilt_position)}
        _post_method(url, headers, payload, f"set tilt position of {entity_id} to {tilt_position}")