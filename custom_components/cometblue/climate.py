"""
Home Assistant Support for Eurotronic CometBlue thermostats.
They are identical to the Sygonix, Xavax Bluetooth thermostats

This version is based on the bluepy library and works on hassio. 
Currently only current and target temperature in manual mode is supported, nothing else. 

Add your cometblue thermostats to configuration.yaml:

climate cometblue:
  platform: cometblue
  devices:
    thermostat1:
      mac: 11:22:33:44:55:66
      pin: 0

"""
import logging
from datetime import timedelta, datetime
import voluptuous as vol

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE, DOMAIN, ClimateEntityFeature, HVACMode,
)
from homeassistant.const import (
    CONF_MAC, CONF_PIN, CONF_DEVICES, ATTR_TEMPERATURE, ATTR_BATTERY_LEVEL,
    ATTR_LOCKED, PRECISION_HALVES, UnitOfTemperature,
)
import homeassistant.helpers.config_validation as cv
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=300)

ATTR_BATTERY_LOW = 'battery_low'
ATTR_OFFSET = 'offset'
ATTR_STATUS = 'status'
ATTR_WINDOW_OPEN = 'window_open'

CONF_FAKE_MANUAL = "fake_manual_mode"

DEVICE_SCHEMA = vol.Schema({
    vol.Required(CONF_MAC): cv.string,
    vol.Optional(CONF_PIN, default=0): cv.positive_int,
    vol.Optional(CONF_FAKE_MANUAL, default=False): cv.boolean,
})

PLATFORM_SCHEMA = vol.Schema({
    vol.Required(CONF_DEVICES): vol.Schema({cv.string: DEVICE_SCHEMA}),
})

SUPPORT_FLAGS = ClimateEntityFeature.TARGET_TEMPERATURE

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    devices = []
    config = entry.data
    for name, device_cfg in config[CONF_DEVICES].items():
        dev = CometBlueThermostat(str(device_cfg[CONF_MAC]), name, int(device_cfg[CONF_PIN]))
        devices.append(dev)
        if device_cfg[CONF_FAKE_MANUAL]:
            dev.fake_manual_mode = True
    async_add_entities(devices)

def device_getter(address):
    return bluetooth.async_ble_device_from_address(async_get_hass(), address, connectable=True)

class CometBlueThermostat(ClimateEntity):
    def __init__(self, _mac, _name, _pin=None):
        from cometblue_lite import CometBlue
        self._mac = _mac
        self._name = _name
        self._pin = _pin
        self._thermostat = CometBlue(_mac, _pin, device_getter=device_getter)
        self._lastupdate = datetime.now() - MIN_TIME_BETWEEN_UPDATES
        self.fake_manual_mode = False

    @property
    def unique_id(self):
        return self._mac

    @property
    def available(self) -> bool:
        return self._thermostat.available

    @property
    def supported_features(self):
        return SUPPORT_FLAGS

    @property
    def name(self):
        return self._name

    @property
    def temperature_unit(self):
        return UnitOfTemperature.CELSIUS

    @property
    def precision(self):
        return PRECISION_HALVES

    @property
    def current_temperature(self):
        return self._thermostat.current_temperature

    @property
    def target_temperature(self):
        return self._thermostat.target_temperature

    async def async_set_temperature(self, **kwargs):
        if ATTR_TEMPERATURE in kwargs:
            temperature = kwargs.get(ATTR_TEMPERATURE)
            self._thermostat.target_temperature = temperature
            if self.fake_manual_mode:
                self._thermostat.target_temperature_high = temperature
                self._thermostat.target_temperature_low = temperature

    @property
    def min_temp(self):
        return 8.0

    @property
    def max_temp(self):
        return 28.0

    @property
    def hvac_mode(self):
        if self._thermostat.is_off:
            return HVACMode.OFF
        elif self._thermostat.manual_mode or self.fake_manual_mode:
            return HVACMode.HEAT
        else:
            return HVACMode.AUTO

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == self.hvac_mode:
            return
        if self.hvac_mode == HVACMode.OFF:
            self._thermostat.is_off = False
        if hvac_mode == HVACMode.AUTO:
            self._thermostat.manual_mode = False
        elif hvac_mode == HVACMode.HEAT:
            self._thermostat.manual_mode = True
        else:
            self._thermostat.is_off = True

    @property
    def hvac_modes(self):
        if self.fake_manual_mode:
            return (HVACMode.HEAT,)
        return (HVACMode.HEAT, HVACMode.AUTO, HVACMode.OFF)

    @property
    def extra_state_attributes(self):
        return {
            ATTR_BATTERY_LEVEL: self._thermostat.battery_level,
            ATTR_BATTERY_LOW: self._thermostat.low_battery,
            ATTR_LOCKED: self._thermostat.locked,
            ATTR_OFFSET: self._thermostat.offset_temperature,
            ATTR_STATUS: self._thermostat.status,
            ATTR_WINDOW_OPEN: self._thermostat.window_open,
            "model_type": self._thermostat.firmware_rev,
        }

    async def async_update(self):
        now = datetime.now()
        if self._thermostat.should_update() or (self._lastupdate + MIN_TIME_BETWEEN_UPDATES < now):
            try:
                await self._thermostat.update()
                self._lastupdate = datetime.now()
            except Exception as ex:
                _LOGGER.warning(f"Updating state for {self._mac} failed: {ex}")
