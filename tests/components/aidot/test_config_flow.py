"""Test the aidot config flow."""

from unittest.mock import AsyncMock, MagicMock

from aidot.exceptions import AidotUserOrPassIncorrect
from aidot.models.device_model import FavoriteEffectPrimitive
from aiohttp import ClientError
import pytest

from homeassistant.components.aidot.const import (
    CONF_EFFECT_SELECTION,
    CONF_EFFECT_SOURCE,
    DOMAIN,
    EFFECT_SOURCE_ALL,
    EFFECT_SOURCE_MANUAL,
    EFFECT_SOURCE_RECOMMENDED,
)
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.const import CONF_COUNTRY_CODE, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import TEST_COUNTRY, TEST_EMAIL, TEST_LOGIN_RESP, TEST_PASSWORD

from tests.common import MockConfigEntry

DHCP_SERVICE_INFO = DhcpServiceInfo(
    hostname="aidot",
    ip="192.168.1.100",
    macaddress="001122334455",
)


async def test_config_flow_cloud_login_success(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test a successful config flow using cloud login."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COUNTRY_CODE: TEST_COUNTRY,
            CONF_USERNAME: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "effect_source"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EFFECT_SOURCE: EFFECT_SOURCE_RECOMMENDED,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"{TEST_EMAIL} {TEST_COUNTRY}"
    assert result["data"] == TEST_LOGIN_RESP
    assert result["options"] == {
        CONF_EFFECT_SOURCE: EFFECT_SOURCE_RECOMMENDED,
        CONF_EFFECT_SELECTION: {},
    }
    assert result["result"].unique_id == TEST_LOGIN_RESP["id"]


async def test_config_flow_effect_source_defaults_to_all(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Test effect source defaults to all effects."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COUNTRY_CODE: TEST_COUNTRY,
            CONF_USERNAME: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "effect_source"
    assert [
        option["value"]
        for option in result["data_schema"]
        .schema[next(iter(result["data_schema"].schema))]
        .config["options"]
    ] == [EFFECT_SOURCE_ALL, EFFECT_SOURCE_RECOMMENDED]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EFFECT_SOURCE: EFFECT_SOURCE_ALL,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {
        CONF_EFFECT_SOURCE: EFFECT_SOURCE_ALL,
        CONF_EFFECT_SELECTION: {},
    }


async def test_options_flow_updates_effect_source(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test options flow updates the effect source."""
    coordinator = MagicMock()
    mock_config_entry.runtime_data = coordinator
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_EFFECT_SOURCE: EFFECT_SOURCE_RECOMMENDED,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_EFFECT_SOURCE: EFFECT_SOURCE_RECOMMENDED}
    coordinator.update_options.assert_called_once_with(
        {CONF_EFFECT_SOURCE: EFFECT_SOURCE_RECOMMENDED}
    )
    mock_setup_entry.assert_not_called()


async def test_options_flow_updates_manual_effect_selection(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test options flow updates manually selected effects."""
    selected_effect = FavoriteEffectPrimitive(name="Sunrise", primitiveEffectId="p_1")
    available_effect = FavoriteEffectPrimitive(name="Party", primitiveEffectId="p_2")
    info = MagicMock()
    info.name = "Test light"
    info.presets = {"Sunrise": selected_effect}
    coordinator = MagicMock()
    coordinator.devices_by_id = {"device_id": {}}
    coordinator.client.get_all_cached_effects.return_value = {
        "Sunrise": selected_effect,
        "Party": available_effect,
    }
    coordinator.device_coordinators = {
        "device_id": MagicMock(device_client=MagicMock(info=info))
    }
    mock_config_entry.runtime_data = coordinator
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_EFFECT_SOURCE: EFFECT_SOURCE_MANUAL,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual_device"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "manual_device": "device_id",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual_effects"
    assert [
        option["value"]
        for option in result["data_schema"]
        .schema[next(iter(result["data_schema"].schema))]
        .config["options"]
    ] == ["p_1", "p_2"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_EFFECT_SELECTION: ["p_1", "p_2"],
        },
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "manual_menu"
    assert result["menu_options"] == [
        "configure_another_light",
        "finish_manual_selection",
    ]
    coordinator.update_options.assert_not_called()

    options = {
        CONF_EFFECT_SOURCE: EFFECT_SOURCE_MANUAL,
        CONF_EFFECT_SELECTION: {"device_id": ["p_1", "p_2"]},
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "next_step_id": "finish_manual_selection",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == options
    coordinator.update_options.assert_called_once_with(options)
    mock_setup_entry.assert_not_called()


async def test_dhcp_discovery(hass: HomeAssistant) -> None:
    """Test DHCP discovery shows the user form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DHCP_SERVICE_INFO,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_dhcp_discovery_aborts_if_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test DHCP discovery aborts when the integration is configured."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DHCP_SERVICE_INFO,
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_dhcp_discovery_aborts_if_already_in_progress(
    hass: HomeAssistant,
) -> None:
    """Test a duplicate DHCP discovery flow aborts."""
    first_result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DHCP_SERVICE_INFO,
    )
    assert first_result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DHCP_SERVICE_INFO,
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (AidotUserOrPassIncorrect, "invalid_auth"),
        (TimeoutError, "cannot_connect"),
        (ClientError, "cannot_connect"),
    ],
)
async def test_config_flow_errors(
    hass: HomeAssistant,
    patch_aidot_client: MagicMock,
    mock_setup_entry: AsyncMock,
    exception: Exception,
    error: str,
) -> None:
    """Test a failed config flow using cloud connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}
    patch_aidot_client.async_post_login.side_effect = exception
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COUNTRY_CODE: TEST_COUNTRY,
            CONF_USERNAME: TEST_EMAIL,
            CONF_PASSWORD: "ErrorPassword",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}

    patch_aidot_client.async_post_login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COUNTRY_CODE: TEST_COUNTRY,
            CONF_USERNAME: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "effect_source"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_EFFECT_SOURCE: EFFECT_SOURCE_ALL,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == TEST_LOGIN_RESP
    assert result["options"] == {
        CONF_EFFECT_SOURCE: EFFECT_SOURCE_ALL,
        CONF_EFFECT_SELECTION: {},
    }


async def test_form_abort_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test we abort if already configured."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_COUNTRY_CODE: TEST_COUNTRY,
            CONF_USERNAME: TEST_EMAIL,
            CONF_PASSWORD: TEST_PASSWORD,
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
