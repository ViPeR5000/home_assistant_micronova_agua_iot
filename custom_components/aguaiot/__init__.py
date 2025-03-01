"""Support for Micronova Agua IOT heating devices."""
import logging
from datetime import timedelta
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, EVENT_HOMEASSISTANT_STOP

from py_agua_iot import (
    ConnectionError,
    Error as AguaIOTError,
    UnauthorizedError,
    agua_iot,
)

from .const import (
    CONF_API_URL,
    CONF_BRAND_ID,
    CONF_CUSTOMER_CODE,
    CONF_LOGIN_API_URL,
    CONF_API_LOGIN_APPLICATION_VERSION,
    CONF_UUID,
    DOMAIN,
    PLATFORMS,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the AguaIOT integration."""
    if DOMAIN in config:
        for entry_config in config[DOMAIN]:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": SOURCE_IMPORT}, data=entry_config
                )
            )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AguaIOT entry."""
    api_url = entry.data[CONF_API_URL]
    customer_code = entry.data[CONF_CUSTOMER_CODE]
    brand_id = entry.data[CONF_BRAND_ID]
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    gen_uuid = entry.data[CONF_UUID]
    login_api_url = (
        entry.data.get(CONF_LOGIN_API_URL)
        if entry.data.get(CONF_LOGIN_API_URL) != ""
        else None
    )
    api_login_application_version = (
        entry.data.get(CONF_API_LOGIN_APPLICATION_VERSION)
        if entry.data.get(CONF_API_LOGIN_APPLICATION_VERSION) != ""
        else "1.6.0"
    )

    try:
        agua = await hass.async_add_executor_job(
            agua_iot,
            api_url,
            customer_code,
            email,
            password,
            gen_uuid,
            login_api_url,
            brand_id,
            False,
            api_login_application_version,
        )
    except UnauthorizedError:
        _LOGGER.error("Wrong credentials for Agua IOT")
        return False
    except ConnectionError:
        _LOGGER.error("Connection to Agua IOT not possible")
        return False
    except AguaIOTError as err:
        _LOGGER.error("Unknown Agua IOT error: %s", err)
        return False

    async def async_update_data():
        """Get the latest data."""
        try:
            await hass.async_add_executor_job(agua.fetch_device_information)
        except UnauthorizedError:
            _LOGGER.error(
                "Wrong credentials for device %s (%s)",
                self.name,
                self._device.id_device,
            )
            return False
        except ConnectionError:
            _LOGGER.error("Connection to Agua IOT not possible")
            return False
        except AguaIOTError as err:
            _LOGGER.error(
                "Failed to update %s (%s), error: %s",
                self.name,
                self._device.id_device,
                err,
            )
            return False

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="aguaiot",
        update_method=async_update_data,
        update_interval=timedelta(seconds=UPDATE_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "agua": agua,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Services
    async def async_close_connection(event: Event) -> None:
        """Close AguaIOT connection on HA Stop."""
        # await agua.close()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_close_connection)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
