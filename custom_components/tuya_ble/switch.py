"""The Tuya BLE integration."""

from __future__ import annotations

from dataclasses import dataclass, field

import logging
from typing import Any, Callable

from homeassistant.components.switch import (
    SwitchEntityDescription,
    SwitchEntity,
    SwitchDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .devices import TuyaBLEData, TuyaBLEEntity, TuyaBLEProductInfo
from .tuya_ble import TuyaBLEDataPointType, TuyaBLEDevice

_LOGGER = logging.getLogger(__name__)


TuyaBLESwitchGetter = (
    Callable[["TuyaBLESwitch", TuyaBLEProductInfo], bool | None] | None
)


TuyaBLESwitchIsAvailable = Callable[["TuyaBLESwitch", TuyaBLEProductInfo], bool] | None


TuyaBLESwitchSetter = Callable[["TuyaBLESwitch", TuyaBLEProductInfo, bool], None] | None


@dataclass
class TuyaBLESwitchMapping:
    """Model a DP, description and default values"""

    dp_id: int
    description: SwitchEntityDescription
    force_add: bool = True
    dp_type: TuyaBLEDataPointType | None = None
    bitmap_mask: bytes | None = None
    is_available: TuyaBLESwitchIsAvailable = None
    getter: TuyaBLESwitchGetter = None
    setter: TuyaBLESwitchSetter = None


def is_fingerbot_in_program_mode(
    self: TuyaBLESwitch, product: TuyaBLEProductInfo
) -> bool:
    result: bool = True
    if product.fingerbot:
        datapoint = self._device.datapoints[product.fingerbot.mode]
        if datapoint:
            result = datapoint.value == 2
    return result


def is_fingerbot_in_switch_mode(
    self: TuyaBLESwitch, product: TuyaBLEProductInfo
) -> bool:
    result: bool = True
    if product.fingerbot:
        datapoint = self._device.datapoints[product.fingerbot.mode]
        if datapoint:
            result = datapoint.value == 1
    return result


def is_water_valve_in_switch_mode(
    self: TuyaBLESwitch, product: TuyaBLEProductInfo
) -> bool:
    result: bool = False
    if product.watervalve:
        result = True
    return result


def get_fingerbot_program_repeat_forever(
    self: TuyaBLESwitch, product: TuyaBLEProductInfo
) -> bool | None:
    result: bool | None = None
    if product.fingerbot and product.fingerbot.program:
        datapoint = self._device.datapoints[product.fingerbot.program]
        if datapoint and isinstance(datapoint.value, bytes):
            repeat_count = int.from_bytes(datapoint.value[0:2], "big")
            result = repeat_count == 0xFFFF
    return result


def set_fingerbot_program_repeat_forever(
    self: TuyaBLESwitch, product: TuyaBLEProductInfo, value: bool
) -> None:
    if product.fingerbot and product.fingerbot.program:
        datapoint = self._device.datapoints[product.fingerbot.program]
        if datapoint and isinstance(datapoint.value, bytes):
            new_value = (
                int.to_bytes(0xFFFF if value else 1, 2, "big") + datapoint.value[2:]
            )
            self._hass.create_task(datapoint.set_value(new_value))


@dataclass
class TuyaBLEFingerbotSwitchMapping(TuyaBLESwitchMapping):
    description: SwitchEntityDescription = field(
        default_factory=lambda: SwitchEntityDescription(
            key="switch",
        )
    )
    is_available: TuyaBLESwitchIsAvailable = is_fingerbot_in_switch_mode


@dataclass
class TuyaBLEWaterValveSwitchMapping(TuyaBLESwitchMapping):
    description: SwitchEntityDescription = field(
        default_factory=lambda: SwitchEntityDescription(
            key="water_valve",
        )
    )
    is_available: TuyaBLESwitchIsAvailable = is_water_valve_in_switch_mode


@dataclass
class TuyaBLEWaterValveWeatherSwitchMapping(TuyaBLESwitchMapping):
    description: SwitchEntityDescription = field(
        default_factory=lambda: SwitchEntityDescription(
            key="weather_switch",
            icon="mdi:cloud-question",
        )
    )


@dataclass
class TuyaBLEReversePositionsMapping(TuyaBLESwitchMapping):
    description: SwitchEntityDescription = field(
        default_factory=lambda: SwitchEntityDescription(
            key="reverse_positions",
            icon="mdi:arrow-up-down-bold",
            entity_category=EntityCategory.CONFIG,
        )
    )
    is_available: TuyaBLESwitchIsAvailable = is_fingerbot_in_switch_mode


@dataclass
class TuyaBLECategorySwitchMapping:
    """Models a dict of products and their mappings"""

    products: dict[str, list[TuyaBLESwitchMapping]] | None = None
    mapping: list[TuyaBLESwitchMapping] | None = None


mapping: dict[str, TuyaBLECategorySwitchMapping] = {
    "sfkzq": TuyaBLECategorySwitchMapping(
        products={
            **dict.fromkeys(
                ["0axr5s0b", "46zia2nz", "1fcnd8xk"],
                [
                    TuyaBLESwitchMapping(
                        dp_id=1,
                        description=SwitchEntityDescription(
                            key="water_valve",
                            entity_registry_enabled_default=True,
                        ),
                    ),
                ],
            ),
            **dict.fromkeys(
                ["nxquc5lb", "svhikeyq"],
                [  # Smart water timer - SOP10
                    TuyaBLEWaterValveSwitchMapping(dp_id=1),
                    TuyaBLEWaterValveWeatherSwitchMapping(dp_id=14),
                ],
            ),
        },
    ),
    "co2bj": TuyaBLECategorySwitchMapping(
        products={
            "59s19z5m": [  # CO2 Detector
                TuyaBLESwitchMapping(
                    dp_id=11,
                    description=SwitchEntityDescription(
                        key="carbon_dioxide_severely_exceed_alarm",
                        icon="mdi:molecule-co2",
                        entity_category=EntityCategory.CONFIG,
                        entity_registry_enabled_default=False,
                    ),
                    bitmap_mask=b"\x01",
                ),
                TuyaBLESwitchMapping(
                    dp_id=11,
                    description=SwitchEntityDescription(
                        key="low_battery_alarm",
                        icon="mdi:battery-alert",
                        entity_category=EntityCategory.CONFIG,
                        entity_registry_enabled_default=False,
                    ),
                    bitmap_mask=b"\x02",
                ),
                TuyaBLESwitchMapping(
                    dp_id=13,
                    description=SwitchEntityDescription(
                        key="carbon_dioxide_alarm_switch",
                        icon="mdi:molecule-co2",
                        entity_category=EntityCategory.CONFIG,
                    ),
                ),
            ],
        },
    ),
    "ms": TuyaBLECategorySwitchMapping(
        products={
            **dict.fromkeys(
                ["ludzroix", "isk2p555", "gumrixyt"],  # Smart Lock
                [
                    TuyaBLESwitchMapping(
                        dp_id=47,
                        description=SwitchEntityDescription(
                            key="lock_motor_state",
                        ),
                    ),
                ],
            ),
            **dict.fromkeys(
                ["uamrw6h3"],  # Smart Fechadura Positivo
                [
                    TuyaBLESwitchMapping(
                        dp_id=47,
                        description=SwitchEntityDescription(
                            key="lock_motor_state",
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=46,
                        description=SwitchEntityDescription(
                            key="manual_lock",
                        ),
                    ),
                ],
            ),
        }
    ),
    "szjqr": TuyaBLECategorySwitchMapping(
        products={
            **dict.fromkeys(
                ["3yqdo5yt", "xhf790if"],  # CubeTouch 1s and II
                [
                    TuyaBLEFingerbotSwitchMapping(dp_id=1),
                    TuyaBLEReversePositionsMapping(dp_id=4),
                ],
            ),
            **dict.fromkeys(
                [
                    "blliqpsj",
                    "ndvkgsrm",
                    "yiihr7zh",
                    "neq16kgd",
                    "6jcvqwh0",
                    "riecov42",
                    "h8kdwywx",
                ],  # Fingerbot Plus
                [
                    TuyaBLEFingerbotSwitchMapping(dp_id=2),
                    TuyaBLEReversePositionsMapping(dp_id=11),
                    TuyaBLESwitchMapping(
                        dp_id=17,
                        description=SwitchEntityDescription(
                            key="manual_control",
                            icon="mdi:gesture-tap-box",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=2,
                        description=SwitchEntityDescription(
                            key="program",
                            icon="mdi:repeat",
                        ),
                        is_available=is_fingerbot_in_program_mode,
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=121,
                        description=SwitchEntityDescription(
                            key="program_repeat_forever",
                            icon="mdi:repeat",
                            entity_category=EntityCategory.CONFIG,
                        ),
                        getter=get_fingerbot_program_repeat_forever,
                        is_available=is_fingerbot_in_program_mode,
                        setter=set_fingerbot_program_repeat_forever,
                    ),
                ],
            ),
            **dict.fromkeys(
                [
                    "ltak7e1p",
                    "y6kttvd6",
                    "yrnk7mnn",
                    "nvr2rocq",
                    "bnt7wajf",
                    "rvdceqjh",
                    "5xhbk964",
                ],  # Fingerbot
                [
                    TuyaBLEFingerbotSwitchMapping(dp_id=2),
                    TuyaBLEReversePositionsMapping(dp_id=11),
                ],
            ),
        },
    ),
    "kg": TuyaBLECategorySwitchMapping(
        products={
            **dict.fromkeys(
                ["mknd4lci", "riecov42", "bs3ubslo"],  # Fingerbot Plus
                [
                    TuyaBLEFingerbotSwitchMapping(dp_id=1),
                    TuyaBLEReversePositionsMapping(dp_id=104),
                    TuyaBLESwitchMapping(
                        dp_id=107,
                        description=SwitchEntityDescription(
                            key="manual_control",
                            icon="mdi:gesture-tap-box",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=1,
                        description=SwitchEntityDescription(
                            key="program",
                            icon="mdi:repeat",
                        ),
                        is_available=is_fingerbot_in_program_mode,
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=109,
                        description=SwitchEntityDescription(
                            key="program_repeat_forever",
                            icon="mdi:repeat",
                            entity_category=EntityCategory.CONFIG,
                        ),
                        getter=get_fingerbot_program_repeat_forever,
                        is_available=is_fingerbot_in_program_mode,
                        setter=set_fingerbot_program_repeat_forever,
                    ),
                ],
            ),
        },
    ),
    "wk": TuyaBLECategorySwitchMapping(
        products={
            **dict.fromkeys(
                [
                    "drlajpqc",
                    "nhj2j7su",
                    "zmachryv",
                ],  # Thermostatic Radiator Valve
                [
                    TuyaBLESwitchMapping(
                        dp_id=8,
                        description=SwitchEntityDescription(
                            key="window_check",
                            icon="mdi:window-closed",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=10,
                        description=SwitchEntityDescription(
                            key="antifreeze",
                            icon="mdi:snowflake-off",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=40,
                        description=SwitchEntityDescription(
                            key="child_lock",
                            icon="mdi:account-lock",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=130,
                        description=SwitchEntityDescription(
                            key="water_scale_proof",
                            icon="mdi:water-check",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=107,
                        description=SwitchEntityDescription(
                            key="programming_mode",
                            icon="mdi:calendar-edit",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=108,
                        description=SwitchEntityDescription(
                            key="programming_switch",
                            icon="mdi:calendar-clock",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                ],
            ),
        },
    ),
    "wsdcg": TuyaBLECategorySwitchMapping(
        products={
            "ojzlzzsw": [  # Soil moisture sensor
                TuyaBLESwitchMapping(
                    dp_id=21,
                    description=SwitchEntityDescription(
                        key="switch",
                        icon="mdi:thermometer",
                        entity_category=EntityCategory.CONFIG,
                        entity_registry_enabled_default=False,
                    ),
                ),
            ],
        },
    ),
    "ggq": TuyaBLECategorySwitchMapping(
        products={
            "6pahkcau": [  # Irrigation computer PARKSIDE PPB A1
                TuyaBLESwitchMapping(
                    dp_id=1,
                    description=SwitchEntityDescription(
                        key="water_valve",
                        entity_registry_enabled_default=True,
                    ),
                ),
            ],
            **dict.fromkeys(
                [
                    "hfgdqhho",
                    "qycalacn",
                    "fnlw6npo",
                    "jjqi2syk",
                ],  # Irrigation computer - dual outlet
                [
                    TuyaBLESwitchMapping(
                        dp_id=105,
                        description=SwitchEntityDescription(
                            key="water_valve_z1",
                            name="CH1 Valve",
                            entity_registry_enabled_default=True,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=104,
                        description=SwitchEntityDescription(
                            key="water_valve_z2",
                            name="CH2 Valve",
                            entity_registry_enabled_default=True,
                        ),
                    ),
                ],
            ),
        },
    ),
    "dcb": TuyaBLECategorySwitchMapping(
        products={
            **dict.fromkeys(
                [
                    "ajrhf1aj",
                    "z5ztlw3k",
                ],
                [  # PARKSIDE Smart battery 8Ah
                    TuyaBLESwitchMapping(
                        dp_id=12,
                        description=SwitchEntityDescription(
                            key="upper_temp_switch",
                            icon="mdi:thermometer-chevron-up",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=22,
                        description=SwitchEntityDescription(
                            key="security_switch",
                            icon="mdi:shield-lock-outline",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=155,
                        description=SwitchEntityDescription(
                            key="kick_back_switch",
                            icon="mdi:car-esp",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=163,
                        description=SwitchEntityDescription(
                            key="lamp_switch",
                            device_class=SwitchDeviceClass.SWITCH,
                            icon="mdi:lightbulb",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=170,
                        description=SwitchEntityDescription(
                            key="cw_or_ccw_control",
                            icon="mdi:rotate-right",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=185,
                        description=SwitchEntityDescription(
                            key="laser_switch",
                            icon="mdi:laser-pointer",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                    TuyaBLESwitchMapping(
                        dp_id=186,
                        description=SwitchEntityDescription(
                            key="laser_pulse_switch",
                            icon="mdi:pulse",
                            entity_category=EntityCategory.CONFIG,
                        ),
                    ),
                ],
            ),
        },
    ),
}


def get_mapping_by_device(device: TuyaBLEDevice) -> list[TuyaBLECategorySwitchMapping]:
    """Lookup mapping for a given device"""
    category = mapping.get(device.category)
    if category is not None and category.products is not None:
        product_mapping = category.products.get(device.product_id)
        if product_mapping is not None:
            return product_mapping
        if category.mapping is not None:
            return category.mapping

    return []


class TuyaBLESwitch(TuyaBLEEntity, SwitchEntity):
    """Representation of a Tuya BLE Switch."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DataUpdateCoordinator,
        device: TuyaBLEDevice,
        product: TuyaBLEProductInfo,
        mapping: TuyaBLESwitchMapping,
    ) -> None:
        super().__init__(hass, coordinator, device, product, mapping.description)
        self._mapping = mapping

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""

        if self._mapping.getter:
            return self._mapping.getter(self, self._product)

        datapoint = self._device.datapoints[self._mapping.dp_id]
        if datapoint:
            if (
                datapoint.type
                in [TuyaBLEDataPointType.DT_RAW, TuyaBLEDataPointType.DT_BITMAP]
                and self._mapping.bitmap_mask
            ):
                bitmap_value = bytes(datapoint.value)
                bitmap_mask = self._mapping.bitmap_mask
                for v, m in zip(bitmap_value, bitmap_mask, strict=True):
                    if (v & m) != 0:
                        return True
            else:
                return bool(datapoint.value)
        return False

    def turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self._mapping.setter:
            return self._mapping.setter(self, self._product, True)

        new_value: bool | bytes
        if self._mapping.bitmap_mask:
            datapoint = self._device.datapoints.get_or_create(
                self._mapping.dp_id,
                TuyaBLEDataPointType.DT_BITMAP,
                self._mapping.bitmap_mask,
            )
            bitmap_mask = self._mapping.bitmap_mask
            bitmap_value = bytes(datapoint.value)
            new_value = bytes(
                v | m for (v, m) in zip(bitmap_value, bitmap_mask, strict=True)
            )
        else:
            datapoint = self._device.datapoints.get_or_create(
                self._mapping.dp_id,
                TuyaBLEDataPointType.DT_BOOL,
                True,
            )
            new_value = True
        if datapoint:
            self._hass.create_task(datapoint.set_value(new_value))

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if self._mapping.setter:
            return self._mapping.setter(self, self._product, False)

        new_value: bool | bytes
        if self._mapping.bitmap_mask:
            datapoint = self._device.datapoints.get_or_create(
                self._mapping.dp_id,
                TuyaBLEDataPointType.DT_BITMAP,
                self._mapping.bitmap_mask,
            )
            bitmap_mask = self._mapping.bitmap_mask
            bitmap_value = bytes(datapoint.value)
            new_value = bytes(
                v & ~m for (v, m) in zip(bitmap_value, bitmap_mask, strict=True)
            )
        else:
            datapoint = self._device.datapoints.get_or_create(
                self._mapping.dp_id,
                TuyaBLEDataPointType.DT_BOOL,
                False,
            )
            new_value = False
        if datapoint:
            self._hass.create_task(datapoint.set_value(new_value))

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        result = super().available
        if result and self._mapping.is_available:
            result = self._mapping.is_available(self, self._product)
        return result


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Tuya BLE sensors."""
    data: TuyaBLEData = hass.data[DOMAIN][entry.entry_id]
    mappings = get_mapping_by_device(data.device)
    entities: list[TuyaBLESwitch] = []
    for mapping in mappings:
        if mapping.force_add or data.device.datapoints.has_id(
            mapping.dp_id, mapping.dp_type
        ):
            entities.append(
                TuyaBLESwitch(
                    hass,
                    data.coordinator,
                    data.device,
                    data.product,
                    mapping,
                )
            )
    async_add_entities(entities)
