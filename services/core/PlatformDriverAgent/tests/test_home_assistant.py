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

import json
import logging
import pytest
import gevent

from volttron.platform.agent.known_identities import (
    PLATFORM_DRIVER,
    CONFIGURATION_STORE,
)
from volttron.platform import get_services_core
from volttron.platform.agent import utils
from volttron.platform.keystore import KeyStore
from volttrontesting.utils.platformwrapper import PlatformWrapper

utils.setup_logging()
logger = logging.getLogger(__name__)

# To run these tests, create a helper toggle named volttrontest in your Home Assistant instance.
# This can be done by going to Settings > Devices & services > Helpers > Create Helper > Toggle
#
# For fan integration tests, set FAN_TEST_ENTITY_ID to your fan entity (e.g., "fan.living_room_fan")
HOMEASSISTANT_TEST_IP = ""
ACCESS_TOKEN = ""
PORT = ""
FAN_TEST_ENTITY_ID = ""  # Set to your fan entity ID for integration tests

skip_msg = "Some configuration variables are not set. Check HOMEASSISTANT_TEST_IP, ACCESS_TOKEN, and PORT"
skip_fan_msg = "Fan integration test requires FAN_TEST_ENTITY_ID to be set"

# Skip condition for integration tests (requires real Home Assistant)
requires_home_assistant = pytest.mark.skipif(
    not (HOMEASSISTANT_TEST_IP and ACCESS_TOKEN and PORT),
    reason=skip_msg
)

# Skip condition for fan integration tests (requires real Home Assistant + fan entity)
requires_fan_entity = pytest.mark.skipif(
    not (HOMEASSISTANT_TEST_IP and ACCESS_TOKEN and PORT and FAN_TEST_ENTITY_ID),
    reason=skip_fan_msg
)

HOMEASSISTANT_DEVICE_TOPIC = "devices/home_assistant"
FAN_DEVICE_TOPIC = "devices/home_assistant_fan"


# Get the point which will should be off
@requires_home_assistant
def test_get_point(volttron_instance, config_store):
    expected_values = 0
    agent = volttron_instance.dynamic_agent
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'get_point', 'home_assistant', 'bool_state').get(timeout=20)
    assert result == expected_values, "The result does not match the expected result."


# The default value for this fake light is 3. If the test cannot reach out to home assistant,
# the value will default to 3 making the test fail.
@requires_home_assistant
def test_data_poll(volttron_instance: PlatformWrapper, config_store):
    expected_values = [{'bool_state': 0}, {'bool_state': 1}]
    agent = volttron_instance.dynamic_agent
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all', 'home_assistant').get(timeout=20)
    assert result in expected_values, "The result does not match the expected result."


# Turn on the light. Light is automatically turned off every 30 seconds to allow test to turn
# it on and receive the correct value.
@requires_home_assistant
def test_set_point(volttron_instance, config_store):
    expected_values = {'bool_state': 1}
    agent = volttron_instance.dynamic_agent
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant', 'bool_state', 1)
    gevent.sleep(10)
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all', 'home_assistant').get(timeout=20)
    assert result == expected_values, "The result does not match the expected result."


@pytest.fixture(scope="module")
def config_store(volttron_instance, platform_driver):

    capabilities = [{"edit_config_store": {"identity": PLATFORM_DRIVER}}]
    volttron_instance.add_capabilities(volttron_instance.dynamic_agent.core.publickey, capabilities)

    registry_config = "homeassistant_test.json"
    registry_obj = [{
        "Entity ID": "input_boolean.volttrontest",
        "Entity Point": "state",
        "Volttron Point Name": "bool_state",
        "Units": "On / Off",
        "Units Details": "off: 0, on: 1",
        "Writable": True,
        "Starting Value": 3,
        "Type": "int",
        "Notes": "lights hallway"
    }]

    volttron_instance.dynamic_agent.vip.rpc.call(CONFIGURATION_STORE,
                                                 "manage_store",
                                                 PLATFORM_DRIVER,
                                                 registry_config,
                                                 json.dumps(registry_obj),
                                                 config_type="json")
    gevent.sleep(2)
    # driver config
    driver_config = {
        "driver_config": {"ip_address": HOMEASSISTANT_TEST_IP, "access_token": ACCESS_TOKEN, "port": PORT},
        "driver_type": "home_assistant",
        "registry_config": f"config://{registry_config}",
        "timezone": "US/Pacific",
        "interval": 30,
    }

    volttron_instance.dynamic_agent.vip.rpc.call(CONFIGURATION_STORE,
                                                 "manage_store",
                                                 PLATFORM_DRIVER,
                                                 HOMEASSISTANT_DEVICE_TOPIC,
                                                 json.dumps(driver_config),
                                                 config_type="json"
                                                 )
    gevent.sleep(2)

    yield platform_driver

    print("Wiping out store.")
    volttron_instance.dynamic_agent.vip.rpc.call(CONFIGURATION_STORE, "manage_delete_store", PLATFORM_DRIVER)
    gevent.sleep(0.1)


@pytest.fixture(scope="module")
def platform_driver(volttron_instance):
    # Start the platform driver agent which would in turn start the bacnet driver
    platform_uuid = volttron_instance.install_agent(
        agent_dir=get_services_core("PlatformDriverAgent"),
        config_file={
            "publish_breadth_first_all": False,
            "publish_depth_first": False,
            "publish_breadth_first": False,
        },
        start=True,
    )
    gevent.sleep(2)  # wait for the agent to start and start the devices
    assert volttron_instance.is_agent_running(platform_uuid)
    yield platform_uuid

    volttron_instance.stop_agent(platform_uuid)
    if not volttron_instance.debug_mode:
        volttron_instance.remove_agent(platform_uuid)


# ============================================================================
# Fan Integration Tests (Requires Real Home Assistant with Fan Entity)
# ============================================================================
# To run these tests:
# 1. Set HOMEASSISTANT_TEST_IP, ACCESS_TOKEN, PORT
# 2. Set FAN_TEST_ENTITY_ID to your fan entity (e.g., "fan.living_room_fan")

@pytest.fixture(scope="module")
def fan_config_store(volttron_instance, platform_driver):
    """Configure the platform driver with fan entity registry for integration tests."""
    capabilities = [{"edit_config_store": {"identity": PLATFORM_DRIVER}}]
    volttron_instance.add_capabilities(volttron_instance.dynamic_agent.core.publickey, capabilities)

    registry_config = "homeassistant_fan_test.json"
    registry_obj = [
        {
            "Entity ID": FAN_TEST_ENTITY_ID,
            "Entity Point": "state",
            "Volttron Point Name": "fan_state",
            "Units": "On / Off",
            "Units Details": "off: 0, on: 1",
            "Writable": True,
            "Starting Value": 0,
            "Type": "int",
            "Notes": "Fan on/off state"
        },
        {
            "Entity ID": FAN_TEST_ENTITY_ID,
            "Entity Point": "percentage",
            "Volttron Point Name": "fan_percentage",
            "Units": "%",
            "Units Details": "0-100",
            "Writable": True,
            "Starting Value": 0,
            "Type": "int",
            "Notes": "Fan speed percentage"
        },
        {
            "Entity ID": FAN_TEST_ENTITY_ID,
            "Entity Point": "oscillating",
            "Volttron Point Name": "fan_oscillating",
            "Units": "On / Off",
            "Units Details": "off: 0, on: 1",
            "Writable": True,
            "Starting Value": 0,
            "Type": "int",
            "Notes": "Fan oscillation"
        }
    ]

    volttron_instance.dynamic_agent.vip.rpc.call(
        CONFIGURATION_STORE,
        "manage_store",
        PLATFORM_DRIVER,
        registry_config,
        json.dumps(registry_obj),
        config_type="json"
    )
    gevent.sleep(2)

    # driver config
    driver_config = {
        "driver_config": {"ip_address": HOMEASSISTANT_TEST_IP, "access_token": ACCESS_TOKEN, "port": PORT},
        "driver_type": "home_assistant",
        "registry_config": f"config://{registry_config}",
        "timezone": "US/Pacific",
        "interval": 30,
    }

    volttron_instance.dynamic_agent.vip.rpc.call(
        CONFIGURATION_STORE,
        "manage_store",
        PLATFORM_DRIVER,
        FAN_DEVICE_TOPIC,
        json.dumps(driver_config),
        config_type="json"
    )
    gevent.sleep(2)

    yield platform_driver

    print("Wiping out fan store.")
    volttron_instance.dynamic_agent.vip.rpc.call(CONFIGURATION_STORE, "manage_delete_store", PLATFORM_DRIVER)
    gevent.sleep(0.1)


# Get the fan state point
@requires_fan_entity
def test_fan_get_point(volttron_instance, fan_config_store):
    """Test getting fan state from real Home Assistant."""
    agent = volttron_instance.dynamic_agent
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'get_point', 'home_assistant_fan', 'fan_state').get(timeout=20)
    assert result in [0, 1], f"Fan state should be 0 or 1, got {result}"


# Poll all fan data points
@requires_fan_entity
def test_fan_data_poll(volttron_instance: PlatformWrapper, fan_config_store):
    """Test scraping all fan data from real Home Assistant."""
    agent = volttron_instance.dynamic_agent
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all', 'home_assistant_fan').get(timeout=20)
    assert 'fan_state' in result, "fan_state should be in scrape_all result"
    assert result['fan_state'] in [0, 1], f"Fan state should be 0 or 1, got {result['fan_state']}"


# Turn on the fan
@requires_fan_entity
def test_fan_set_state_on(volttron_instance, fan_config_store):
    """Test turning on fan via real Home Assistant."""
    agent = volttron_instance.dynamic_agent
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_fan', 'fan_state', 1)
    gevent.sleep(5)
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all', 'home_assistant_fan').get(timeout=20)
    assert result['fan_state'] == 1, f"Fan should be on (1), got {result['fan_state']}"


# Turn off the fan
@requires_fan_entity
def test_fan_set_state_off(volttron_instance, fan_config_store):
    """Test turning off fan via real Home Assistant."""
    agent = volttron_instance.dynamic_agent
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_fan', 'fan_state', 0)
    gevent.sleep(5)
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all', 'home_assistant_fan').get(timeout=20)
    assert result['fan_state'] == 0, f"Fan should be off (0), got {result['fan_state']}"


# Set fan speed percentage
@requires_fan_entity
def test_fan_set_percentage(volttron_instance, fan_config_store):
    """Test setting fan speed percentage via real Home Assistant."""
    agent = volttron_instance.dynamic_agent
    # Turn on fan first
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_fan', 'fan_state', 1)
    gevent.sleep(3)
    # Set speed to 50%
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_fan', 'fan_percentage', 50)
    gevent.sleep(5)
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all', 'home_assistant_fan').get(timeout=20)
    # Note: Some fans round percentage to supported speed steps
    assert result.get('fan_percentage') is not None, "fan_percentage should be present"
    logger.info(f"Fan percentage result: {result.get('fan_percentage')}")
    # Clean up - turn off fan
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_fan', 'fan_state', 0)


# Set fan oscillation
@requires_fan_entity
def test_fan_set_oscillation(volttron_instance, fan_config_store):
    """Test setting fan oscillation via real Home Assistant."""
    agent = volttron_instance.dynamic_agent
    # Turn on fan first
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_fan', 'fan_state', 1)
    gevent.sleep(3)
    # Enable oscillation
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_fan', 'fan_oscillating', 1)
    gevent.sleep(5)
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all', 'home_assistant_fan').get(timeout=20)
    logger.info(f"Fan oscillating result: {result.get('fan_oscillating')}")
    # Clean up - turn off fan
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_fan', 'fan_state', 0)


# ============================================================================
# Fan Unit Tests (Mocked - No Real Home Assistant Required)
# ============================================================================

from unittest.mock import patch, MagicMock, Mock
import sys
import os

# Add the interfaces path for importing the module directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'platform_driver', 'interfaces'))


@pytest.fixture
def mock_interface():
    """Create a mocked Home Assistant interface for fan testing."""
    from platform_driver.interfaces.home_assistant import Interface

    interface = Interface()
    interface.ip_address = "192.168.1.100"
    interface.access_token = "test_token"
    interface.port = "8123"
    interface.units = "F"
    return interface


@pytest.fixture
def fan_registry_config():
    """Fan registry configuration for testing."""
    return [
        {
            "Entity ID": "fan.test_fan",
            "Entity Point": "state",
            "Volttron Point Name": "fan_state",
            "Units": "On / Off",
            "Writable": True,
            "Type": "int",
        },
        {
            "Entity ID": "fan.test_fan",
            "Entity Point": "percentage",
            "Volttron Point Name": "fan_percentage",
            "Units": "%",
            "Writable": True,
            "Type": "int",
        },
        {
            "Entity ID": "fan.test_fan",
            "Entity Point": "preset_mode",
            "Volttron Point Name": "fan_preset_mode",
            "Units": "",
            "Writable": True,
            "Type": "string",
        },
        {
            "Entity ID": "fan.test_fan",
            "Entity Point": "direction",
            "Volttron Point Name": "fan_direction",
            "Units": "",
            "Writable": True,
            "Type": "string",
        },
        {
            "Entity ID": "fan.test_fan",
            "Entity Point": "oscillating",
            "Volttron Point Name": "fan_oscillating",
            "Units": "On / Off",
            "Writable": True,
            "Type": "int",
        },
    ]


class TestFanMocked:
    """Mocked unit tests for Fan entity write-access. No real Home Assistant required."""

    def test_turn_on_fan(self, mock_interface):
        """Test turn_on_fan method calls correct API endpoint."""
        with patch('platform_driver.interfaces.home_assistant.requests.post') as mock_post:
            mock_post.return_value.status_code = 200

            mock_interface.turn_on_fan("fan.test_fan")

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/services/fan/turn_on" in call_args[0][0]
            assert call_args[1]['json']['entity_id'] == "fan.test_fan"

    def test_turn_on_fan_with_percentage(self, mock_interface):
        """Test turn_on_fan method with percentage parameter."""
        with patch('platform_driver.interfaces.home_assistant.requests.post') as mock_post:
            mock_post.return_value.status_code = 200

            mock_interface.turn_on_fan("fan.test_fan", percentage=50)

            call_args = mock_post.call_args
            assert call_args[1]['json']['entity_id'] == "fan.test_fan"
            assert call_args[1]['json']['percentage'] == 50

    def test_turn_on_fan_with_preset_mode(self, mock_interface):
        """Test turn_on_fan method with preset_mode parameter."""
        with patch('platform_driver.interfaces.home_assistant.requests.post') as mock_post:
            mock_post.return_value.status_code = 200

            mock_interface.turn_on_fan("fan.test_fan", preset_mode="auto")

            call_args = mock_post.call_args
            assert call_args[1]['json']['entity_id'] == "fan.test_fan"
            assert call_args[1]['json']['preset_mode'] == "auto"

    def test_turn_off_fan(self, mock_interface):
        """Test turn_off_fan method calls correct API endpoint."""
        with patch('platform_driver.interfaces.home_assistant.requests.post') as mock_post:
            mock_post.return_value.status_code = 200

            mock_interface.turn_off_fan("fan.test_fan")

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/services/fan/turn_off" in call_args[0][0]
            assert call_args[1]['json']['entity_id'] == "fan.test_fan"

    def test_set_fan_percentage(self, mock_interface):
        """Test set_fan_percentage method calls correct API endpoint."""
        with patch('platform_driver.interfaces.home_assistant.requests.post') as mock_post:
            mock_post.return_value.status_code = 200

            mock_interface.set_fan_percentage("fan.test_fan", 75)

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/services/fan/set_percentage" in call_args[0][0]
            assert call_args[1]['json']['entity_id'] == "fan.test_fan"
            assert call_args[1]['json']['percentage'] == 75

    def test_set_fan_percentage_invalid_entity(self, mock_interface):
        """Test set_fan_percentage rejects non-fan entities."""
        with pytest.raises(ValueError) as exc_info:
            mock_interface.set_fan_percentage("light.test_light", 50)
        assert "not a valid fan entity ID" in str(exc_info.value)

    def test_set_fan_preset_mode(self, mock_interface):
        """Test set_fan_preset_mode method calls correct API endpoint."""
        with patch('platform_driver.interfaces.home_assistant.requests.post') as mock_post:
            mock_post.return_value.status_code = 200

            mock_interface.set_fan_preset_mode("fan.test_fan", "High")

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/services/fan/set_preset_mode" in call_args[0][0]
            assert call_args[1]['json']['entity_id'] == "fan.test_fan"
            assert call_args[1]['json']['preset_mode'] == "High"

    def test_set_fan_preset_mode_invalid_entity(self, mock_interface):
        """Test set_fan_preset_mode rejects non-fan entities."""
        with pytest.raises(ValueError) as exc_info:
            mock_interface.set_fan_preset_mode("climate.thermostat", "auto")
        assert "not a valid fan entity ID" in str(exc_info.value)

    def test_set_fan_direction_forward(self, mock_interface):
        """Test set_fan_direction method with forward direction."""
        with patch('platform_driver.interfaces.home_assistant.requests.post') as mock_post:
            mock_post.return_value.status_code = 200

            mock_interface.set_fan_direction("fan.test_fan", "forward")

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/services/fan/set_direction" in call_args[0][0]
            assert call_args[1]['json']['entity_id'] == "fan.test_fan"
            assert call_args[1]['json']['direction'] == "forward"

    def test_set_fan_direction_reverse(self, mock_interface):
        """Test set_fan_direction method with reverse direction."""
        with patch('platform_driver.interfaces.home_assistant.requests.post') as mock_post:
            mock_post.return_value.status_code = 200

            mock_interface.set_fan_direction("fan.test_fan", "reverse")

            call_args = mock_post.call_args
            assert call_args[1]['json']['direction'] == "reverse"

    def test_set_fan_direction_invalid(self, mock_interface):
        """Test set_fan_direction rejects invalid directions."""
        with pytest.raises(ValueError) as exc_info:
            mock_interface.set_fan_direction("fan.test_fan", "sideways")
        assert "Must be 'forward' or 'reverse'" in str(exc_info.value)

    def test_set_fan_direction_invalid_entity(self, mock_interface):
        """Test set_fan_direction rejects non-fan entities."""
        with pytest.raises(ValueError) as exc_info:
            mock_interface.set_fan_direction("switch.test", "forward")
        assert "not a valid fan entity ID" in str(exc_info.value)

    def test_set_fan_oscillation_on(self, mock_interface):
        """Test set_fan_oscillation method with oscillation enabled."""
        with patch('platform_driver.interfaces.home_assistant.requests.post') as mock_post:
            mock_post.return_value.status_code = 200

            mock_interface.set_fan_oscillation("fan.test_fan", True)

            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/api/services/fan/oscillate" in call_args[0][0]
            assert call_args[1]['json']['entity_id'] == "fan.test_fan"
            assert call_args[1]['json']['oscillating'] is True

    def test_set_fan_oscillation_off(self, mock_interface):
        """Test set_fan_oscillation method with oscillation disabled."""
        with patch('platform_driver.interfaces.home_assistant.requests.post') as mock_post:
            mock_post.return_value.status_code = 200

            mock_interface.set_fan_oscillation("fan.test_fan", False)

            call_args = mock_post.call_args
            assert call_args[1]['json']['oscillating'] is False

    def test_set_fan_oscillation_invalid_entity(self, mock_interface):
        """Test set_fan_oscillation rejects non-fan entities."""
        with pytest.raises(ValueError) as exc_info:
            mock_interface.set_fan_oscillation("light.test", True)
        assert "not a valid fan entity ID" in str(exc_info.value)

    def test_set_point_fan_state_on(self, mock_interface, fan_registry_config):
        """Test _set_point for fan state on."""
        mock_interface.parse_config(fan_registry_config)

        with patch.object(mock_interface, 'turn_on_fan') as mock_turn_on:
            result = mock_interface._set_point("fan_state", 1)
            mock_turn_on.assert_called_once_with("fan.test_fan")
            assert result == 1

    def test_set_point_fan_state_off(self, mock_interface, fan_registry_config):
        """Test _set_point for fan state off."""
        mock_interface.parse_config(fan_registry_config)

        with patch.object(mock_interface, 'turn_off_fan') as mock_turn_off:
            result = mock_interface._set_point("fan_state", 0)
            mock_turn_off.assert_called_once_with("fan.test_fan")
            assert result == 0

    def test_set_point_fan_state_invalid(self, mock_interface, fan_registry_config):
        """Test _set_point rejects invalid fan state values."""
        mock_interface.parse_config(fan_registry_config)

        with pytest.raises(ValueError) as exc_info:
            mock_interface._set_point("fan_state", 5)
        assert "should be an integer value of 1 or 0" in str(exc_info.value)

    def test_set_point_fan_percentage(self, mock_interface, fan_registry_config):
        """Test _set_point for fan percentage."""
        mock_interface.parse_config(fan_registry_config)

        with patch.object(mock_interface, 'set_fan_percentage') as mock_set_pct:
            result = mock_interface._set_point("fan_percentage", 50)
            mock_set_pct.assert_called_once_with("fan.test_fan", 50)
            assert result == 50

    def test_set_point_fan_percentage_invalid(self, mock_interface, fan_registry_config):
        """Test _set_point rejects invalid fan percentage values."""
        mock_interface.parse_config(fan_registry_config)

        with pytest.raises(ValueError) as exc_info:
            mock_interface._set_point("fan_percentage", 150)
        assert "should be an integer between 0 and 100" in str(exc_info.value)

    def test_set_point_fan_preset_mode(self, mock_interface, fan_registry_config):
        """Test _set_point for fan preset mode."""
        mock_interface.parse_config(fan_registry_config)

        with patch.object(mock_interface, 'set_fan_preset_mode') as mock_set_mode:
            result = mock_interface._set_point("fan_preset_mode", "High")
            mock_set_mode.assert_called_once_with("fan.test_fan", "High")
            assert result == "High"

    def test_set_point_fan_direction(self, mock_interface, fan_registry_config):
        """Test _set_point for fan direction."""
        mock_interface.parse_config(fan_registry_config)

        with patch.object(mock_interface, 'set_fan_direction') as mock_set_dir:
            result = mock_interface._set_point("fan_direction", "reverse")
            mock_set_dir.assert_called_once_with("fan.test_fan", "reverse")
            assert result == "reverse"

    def test_set_point_fan_direction_invalid(self, mock_interface, fan_registry_config):
        """Test _set_point rejects invalid fan direction values."""
        mock_interface.parse_config(fan_registry_config)

        with pytest.raises(ValueError) as exc_info:
            mock_interface._set_point("fan_direction", "upward")
        assert "'forward' or 'reverse'" in str(exc_info.value)

    def test_set_point_fan_oscillating(self, mock_interface, fan_registry_config):
        """Test _set_point for fan oscillation."""
        mock_interface.parse_config(fan_registry_config)

        with patch.object(mock_interface, 'set_fan_oscillation') as mock_set_osc:
            result = mock_interface._set_point("fan_oscillating", 1)
            mock_set_osc.assert_called_once_with("fan.test_fan", True)
            assert result == 1

    def test_set_point_fan_oscillating_off(self, mock_interface, fan_registry_config):
        """Test _set_point for fan oscillation off."""
        mock_interface.parse_config(fan_registry_config)

        with patch.object(mock_interface, 'set_fan_oscillation') as mock_set_osc:
            result = mock_interface._set_point("fan_oscillating", 0)
            mock_set_osc.assert_called_once_with("fan.test_fan", False)
            assert result == 0

    def test_scrape_all_fan_state_on(self, mock_interface, fan_registry_config):
        """Test _scrape_all correctly reads fan state as on."""
        mock_interface.parse_config(fan_registry_config)

        mock_entity_data = {
            "state": "on",
            "attributes": {
                "percentage": 75,
                "preset_mode": "High",
                "direction": "forward",
                "oscillating": True,
            }
        }

        with patch.object(mock_interface, 'get_entity_data', return_value=mock_entity_data):
            result = mock_interface._scrape_all()

            assert result['fan_state'] == 1
            assert result['fan_percentage'] == 75
            assert result['fan_preset_mode'] == "High"
            assert result['fan_direction'] == "forward"
            assert result['fan_oscillating'] == 1

    def test_scrape_all_fan_state_off(self, mock_interface, fan_registry_config):
        """Test _scrape_all correctly reads fan state as off."""
        mock_interface.parse_config(fan_registry_config)

        mock_entity_data = {
            "state": "off",
            "attributes": {
                "percentage": 0,
                "preset_mode": None,
                "direction": "forward",
                "oscillating": False,
            }
        }

        with patch.object(mock_interface, 'get_entity_data', return_value=mock_entity_data):
            result = mock_interface._scrape_all()

            assert result['fan_state'] == 0
            assert result['fan_percentage'] == 0
            assert result['fan_oscillating'] == 0

    def test_api_error_handling(self, mock_interface):
        """Test that API errors are properly raised."""
        with patch('platform_driver.interfaces.home_assistant.requests.post') as mock_post:
            mock_post.return_value.status_code = 500
            mock_post.return_value.text = "Internal Server Error"

            with pytest.raises(Exception) as exc_info:
                mock_interface.turn_on_fan("fan.test_fan")
            assert "500" in str(exc_info.value)

    def test_request_exception_handling(self, mock_interface):
        """Test that request exceptions are properly handled."""
        import requests

        with patch('platform_driver.interfaces.home_assistant.requests.post') as mock_post:
            mock_post.side_effect = requests.RequestException("Connection failed")

            with pytest.raises(Exception) as exc_info:
                mock_interface.turn_on_fan("fan.test_fan")
            assert "Connection failed" in str(exc_info.value)
