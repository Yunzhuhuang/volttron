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
from unittest.mock import Mock, patch, MagicMock
import sys
import os

from volttron.platform.agent.known_identities import (
    PLATFORM_DRIVER,
    CONFIGURATION_STORE,
)
from volttron.platform import get_services_core
from volttron.platform.agent import utils
from volttron.platform.keystore import KeyStore
from volttrontesting.utils.platformwrapper import PlatformWrapper

# Import the interface for unit testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'platform_driver', 'interfaces'))
from home_assistant import Interface, HomeAssistantRegister

utils.setup_logging()
logger = logging.getLogger(__name__)

# To run integration tests, create a helper toggle named volttrontest in your Home Assistant instance.
# This can be done by going to Settings > Devices & services > Helpers > Create Helper > Toggle
HOMEASSISTANT_TEST_IP = ""
ACCESS_TOKEN = ""
PORT = ""

skip_msg = "Some configuration variables are not set. Check HOMEASSISTANT_TEST_IP, ACCESS_TOKEN, and PORT"

# Skip marker for integration tests (applied individually, not at module level)
skip_integration = pytest.mark.skipif(
    not (HOMEASSISTANT_TEST_IP and ACCESS_TOKEN and PORT),
    reason=skip_msg
)
HOMEASSISTANT_DEVICE_TOPIC = "devices/home_assistant"


# ==============================
# Unit Tests (No Home Assistant Instance Required)
# ==============================

class TestHomeAssistantCoverUnitTests:
    """Unit tests for Home Assistant cover functionality using mocks"""

    @pytest.fixture
    def interface(self):
        """Create a mock Home Assistant interface"""
        interface = Interface()
        interface.ip_address = "192.168.1.100"
        interface.access_token = "test_token"
        interface.port = "8123"
        return interface

    @pytest.fixture
    def cover_register(self):
        """Create a mock cover register"""
        register = HomeAssistantRegister(
            read_only=False,
            pointName="cover_state",
            units="Open/Closed",
            reg_type=int,
            attributes={},
            entity_id="cover.test_cover",
            entity_point="state"
        )
        return register

    @patch('home_assistant.requests.post')
    def test_unit_open_cover(self, mock_post, interface):
        """Unit test: opening a cover"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        interface.open_cover("cover.test_cover")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "cover/open_cover" in call_args[0][0]
        assert call_args[1]['json']['entity_id'] == "cover.test_cover"

    @patch('home_assistant.requests.post')
    def test_unit_close_cover(self, mock_post, interface):
        """Unit test: closing a cover"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        interface.close_cover("cover.test_cover")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "cover/close_cover" in call_args[0][0]

    @patch('home_assistant.requests.post')
    def test_unit_stop_cover(self, mock_post, interface):
        """Unit test: stopping a cover"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        interface.stop_cover("cover.test_cover")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "cover/stop_cover" in call_args[0][0]

    @patch('home_assistant.requests.post')
    def test_unit_set_cover_position(self, mock_post, interface):
        """Unit test: setting cover position"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        interface.set_cover_position("cover.test_cover", 50)

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "cover/set_cover_position" in call_args[0][0]
        assert call_args[1]['json']['position'] == 50

    @patch('home_assistant.requests.post')
    def test_unit_set_cover_tilt(self, mock_post, interface):
        """Unit test: setting cover tilt position"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        interface.set_cover_tilt_position("cover.test_cover", 75)

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "cover/set_cover_tilt_position" in call_args[0][0]
        assert call_args[1]['json']['tilt_position'] == 75

    def test_unit_invalid_entity(self, interface):
        """Unit test: invalid entity type raises error"""
        with pytest.raises(ValueError) as exc_info:
            interface.open_cover("light.invalid")
        assert "not a valid cover entity ID" in str(exc_info.value)

    def test_unit_position_out_of_range(self, interface):
        """Unit test: position out of range raises error"""
        with pytest.raises(ValueError) as exc_info:
            interface.set_cover_position("cover.test_cover", 150)
        assert "between 0 and 100" in str(exc_info.value)

    def test_unit_position_negative(self, interface):
        """Unit test: negative position raises error"""
        with pytest.raises(ValueError) as exc_info:
            interface.set_cover_position("cover.test_cover", -10)
        assert "between 0 and 100" in str(exc_info.value)

    def test_unit_tilt_out_of_range(self, interface):
        """Unit test: tilt position out of range raises error"""
        with pytest.raises(ValueError) as exc_info:
            interface.set_cover_tilt_position("cover.test_cover", 101)
        assert "between 0 and 100" in str(exc_info.value)

    @patch('home_assistant.Interface.get_register_by_name')
    @patch('home_assistant.Interface.close_cover')
    def test_unit_set_point_close(self, mock_close, mock_get_register, interface, cover_register):
        """Unit test: _set_point closes cover with value 0"""
        cover_register.read_only = False
        mock_get_register.return_value = cover_register
        result = interface._set_point("cover_state", 0)
        mock_close.assert_called_once_with("cover.test_cover")
        assert result == 0

    @patch('home_assistant.Interface.get_register_by_name')
    @patch('home_assistant.Interface.open_cover')
    def test_unit_set_point_open(self, mock_open, mock_get_register, interface, cover_register):
        """Unit test: _set_point opens cover with value 1"""
        cover_register.read_only = False
        mock_get_register.return_value = cover_register
        result = interface._set_point("cover_state", 1)
        mock_open.assert_called_once_with("cover.test_cover")
        assert result == 1

    @patch('home_assistant.Interface.get_register_by_name')
    @patch('home_assistant.Interface.stop_cover')
    def test_unit_set_point_stop(self, mock_stop, mock_get_register, interface, cover_register):
        """Unit test: _set_point stops cover with value 2"""
        cover_register.read_only = False
        mock_get_register.return_value = cover_register
        result = interface._set_point("cover_state", 2)
        mock_stop.assert_called_once_with("cover.test_cover")
        assert result == 2

    @patch('home_assistant.Interface.get_register_by_name')
    def test_unit_set_point_invalid_state(self, mock_get_register, interface, cover_register):
        """Unit test: _set_point with invalid state raises error"""
        cover_register.read_only = False
        mock_get_register.return_value = cover_register
        with pytest.raises(ValueError) as exc_info:
            interface._set_point("cover_state", 5)
        assert "Cover state should be an integer value" in str(exc_info.value)

    @patch('home_assistant.requests.get')
    def test_unit_scrape_cover_open(self, mock_get, interface):
        """Unit test: _scrape_all correctly maps 'open' state to 1"""
        cover_register = HomeAssistantRegister(
            read_only=True,
            pointName="cover_state",
            units="Open/Closed",
            reg_type=int,
            attributes={},
            entity_id="cover.test_cover",
            entity_point="state"
        )
        interface.insert_register(cover_register)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "state": "open",
            "attributes": {"current_position": 100}
        }
        mock_get.return_value = mock_response

        result = interface._scrape_all()
        assert result["cover_state"] == 1

    @patch('home_assistant.requests.get')
    def test_unit_scrape_cover_closed(self, mock_get, interface):
        """Unit test: _scrape_all correctly maps 'closed' state to 0"""
        cover_register = HomeAssistantRegister(
            read_only=True,
            pointName="cover_state",
            units="Open/Closed",
            reg_type=int,
            attributes={},
            entity_id="cover.test_cover",
            entity_point="state"
        )
        interface.insert_register(cover_register)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "state": "closed",
            "attributes": {"current_position": 0}
        }
        mock_get.return_value = mock_response

        result = interface._scrape_all()
        assert result["cover_state"] == 0

    @patch('home_assistant.requests.get')
    def test_unit_scrape_cover_position(self, mock_get, interface):
        """Unit test: _scrape_all correctly reads position attribute"""
        position_register = HomeAssistantRegister(
            read_only=True,
            pointName="cover_position",
            units="Percentage",
            reg_type=int,
            attributes={},
            entity_id="cover.test_cover",
            entity_point="current_position"
        )
        interface.insert_register(position_register)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "state": "open",
            "attributes": {"current_position": 50}
        }
        mock_get.return_value = mock_response

        result = interface._scrape_all()
        assert result["cover_position"] == 50


# ==============================
# Integration Tests (Require Home Assistant Instance)
# ==============================

# Get the point which will should be off
@skip_integration
def test_get_point(volttron_instance, config_store):
    expected_values = 0
    agent = volttron_instance.dynamic_agent
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'get_point', 'home_assistant', 'bool_state').get(timeout=20)
    assert result == expected_values, "The result does not match the expected result."


# The default value for this fake light is 3. If the test cannot reach out to home assistant,
# the value will default to 3 making the test fail.
@skip_integration
def test_data_poll(volttron_instance: PlatformWrapper, config_store):
    expected_values = [{'bool_state': 0}, {'bool_state': 1}]
    agent = volttron_instance.dynamic_agent
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all', 'home_assistant').get(timeout=20)
    assert result in expected_values, "The result does not match the expected result."


# Turn on the light. Light is automatically turned off every 30 seconds to allow test to turn
# it on and receive the correct value.
@skip_integration
def test_set_point(volttron_instance, config_store):
    expected_values = {'bool_state': 1}
    agent = volttron_instance.dynamic_agent
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant', 'bool_state', 1)
    gevent.sleep(10)
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all', 'home_assistant').get(timeout=20)
    assert result == expected_values, "The result does not match the expected result."


# ==============================
# Cover Tests
# ==============================
# Note: To run cover tests, you need to create a helper cover in Home Assistant.
# Go to Settings > Devices & services > Helpers > Create Helper > Cover Template
# Name it 'volttroncover' and configure it with basic open/close functionality.

# Skip cover tests if cover-specific variables are not set
HOMEASSISTANT_COVER_TEST = ""  # Set to "yes" to enable cover tests
cover_skip_msg = "Cover tests disabled. Set HOMEASSISTANT_COVER_TEST='yes' and create a cover.volttroncover entity in Home Assistant"

pytestmark_cover = pytest.mark.skipif(
    not HOMEASSISTANT_COVER_TEST,
    reason=cover_skip_msg
)


@pytestmark_cover
def test_cover_get_state(volttron_instance, config_store_cover):
    """Test getting cover state"""
    agent = volttron_instance.dynamic_agent
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'get_point', 'home_assistant_cover', 'cover_state').get(timeout=20)
    # Result should be 0 (closed) or 1 (open)
    assert result in [0, 1], f"Cover state should be 0 or 1, got {result}"


@pytestmark_cover
def test_cover_get_position(volttron_instance, config_store_cover):
    """Test getting cover position"""
    agent = volttron_instance.dynamic_agent
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'get_point', 'home_assistant_cover', 'cover_position').get(timeout=20)
    # Result should be between 0 and 100
    assert isinstance(result, (int, float)) and 0 <= result <= 100, f"Cover position should be 0-100, got {result}"


@pytestmark_cover
def test_cover_scrape_all(volttron_instance, config_store_cover):
    """Test scraping all cover data"""
    agent = volttron_instance.dynamic_agent
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'scrape_all', 'home_assistant_cover').get(timeout=20)
    assert 'cover_state' in result, "cover_state should be in scraped data"
    assert 'cover_position' in result, "cover_position should be in scraped data"
    assert result['cover_state'] in [0, 1], f"Cover state should be 0 or 1, got {result['cover_state']}"
    assert 0 <= result['cover_position'] <= 100, f"Cover position should be 0-100, got {result['cover_position']}"


@pytestmark_cover
def test_cover_open(volttron_instance, config_store_cover):
    """Test opening a cover"""
    agent = volttron_instance.dynamic_agent
    # Open the cover
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_cover', 'cover_state', 1)
    gevent.sleep(10)  # Wait for cover to open
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'get_point', 'home_assistant_cover', 'cover_state').get(timeout=20)
    assert result == 1, f"Cover should be open (1), got {result}"


@pytestmark_cover
def test_cover_close(volttron_instance, config_store_cover):
    """Test closing a cover"""
    agent = volttron_instance.dynamic_agent
    # Close the cover
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_cover', 'cover_state', 0)
    gevent.sleep(10)  # Wait for cover to close
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'get_point', 'home_assistant_cover', 'cover_state').get(timeout=20)
    assert result == 0, f"Cover should be closed (0), got {result}"


@pytestmark_cover
def test_cover_set_position(volttron_instance, config_store_cover):
    """Test setting cover position"""
    agent = volttron_instance.dynamic_agent
    # Set cover to 50% position
    agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_cover', 'cover_position', 50)
    gevent.sleep(10)  # Wait for cover to move
    result = agent.vip.rpc.call(PLATFORM_DRIVER, 'get_point', 'home_assistant_cover', 'cover_position').get(timeout=20)
    # Allow some tolerance for position (within 5%)
    assert 45 <= result <= 55, f"Cover position should be around 50, got {result}"


@pytestmark_cover
def test_cover_invalid_state(volttron_instance, config_store_cover):
    """Test that invalid cover state values raise an error"""
    agent = volttron_instance.dynamic_agent
    with pytest.raises(Exception) as exc_info:
        agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_cover', 'cover_state', 5).get(timeout=20)
    assert "Cover state should be an integer value" in str(exc_info.value)


@pytestmark_cover
def test_cover_invalid_position(volttron_instance, config_store_cover):
    """Test that invalid cover position values raise an error"""
    agent = volttron_instance.dynamic_agent
    with pytest.raises(Exception) as exc_info:
        agent.vip.rpc.call(PLATFORM_DRIVER, 'set_point', 'home_assistant_cover', 'cover_position', 150).get(timeout=20)
    assert "Cover position should be a number between 0 and 100" in str(exc_info.value)


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
def config_store_cover(volttron_instance, platform_driver):
    """Fixture for cover-specific configuration"""
    capabilities = [{"edit_config_store": {"identity": PLATFORM_DRIVER}}]
    volttron_instance.add_capabilities(volttron_instance.dynamic_agent.core.publickey, capabilities)

    # Registry configuration for cover
    registry_config = "homeassistant_cover_test.json"
    registry_obj = [
        {
            "Entity ID": "cover.volttroncover",
            "Entity Point": "state",
            "Volttron Point Name": "cover_state",
            "Units": "Open / Closed",
            "Units Details": "0: closed, 1: open, 2: stop",
            "Writable": True,
            "Starting Value": 0,
            "Type": "int",
            "Notes": "Cover state control"
        },
        {
            "Entity ID": "cover.volttroncover",
            "Entity Point": "current_position",
            "Volttron Point Name": "cover_position",
            "Units": "Percentage",
            "Units Details": "0-100, where 0=closed and 100=fully open",
            "Writable": True,
            "Starting Value": 0,
            "Type": "int",
            "Notes": "Cover position control (0-100)"
        }
    ]

    volttron_instance.dynamic_agent.vip.rpc.call(CONFIGURATION_STORE,
                                                 "manage_store",
                                                 PLATFORM_DRIVER,
                                                 registry_config,
                                                 json.dumps(registry_obj),
                                                 config_type="json")
    gevent.sleep(2)

    # Driver config for cover
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
                                                 "devices/home_assistant_cover",
                                                 json.dumps(driver_config),
                                                 config_type="json"
                                                 )
    gevent.sleep(2)

    yield platform_driver

    print("Wiping out cover config store.")
    # Clean up only the cover-specific configs
    volttron_instance.dynamic_agent.vip.rpc.call(CONFIGURATION_STORE,
                                                  "manage_delete_config",
                                                  PLATFORM_DRIVER,
                                                  "devices/home_assistant_cover")
    volttron_instance.dynamic_agent.vip.rpc.call(CONFIGURATION_STORE,
                                                  "manage_delete_config",
                                                  PLATFORM_DRIVER,
                                                  registry_config)
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
