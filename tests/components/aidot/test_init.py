"""Test aidot."""

from unittest.mock import MagicMock

from aidot.exceptions import AidotUserOrPassIncorrect

from homeassistant.components.aidot.const import (
    CONF_EFFECT_SOURCE,
    EFFECT_SOURCE_RECOMMENDED,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from . import async_init_integration
from .const import TEST_EMAIL, TEST_LOGIN_RESP

from tests.common import MockConfigEntry


async def test_async_unload_entry(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Test that async_unload_entry unloads the component correctly."""
    await async_init_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_async_setup_entry_auth_failed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    patch_aidot_client: MagicMock,
) -> None:
    """Test setup fails with auth error when login raises."""
    patch_aidot_client.login_info = {}
    patch_aidot_client.async_post_login.side_effect = AidotUserOrPassIncorrect()

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_async_setup_entry_passes_options_to_client(
    hass: HomeAssistant,
    patch_aidot_client: MagicMock,
) -> None:
    """Test setup passes configured options to the client."""
    mock_config_entry = MockConfigEntry(
        domain="aidot",
        unique_id=TEST_LOGIN_RESP["id"],
        title=TEST_EMAIL,
        data=TEST_LOGIN_RESP.copy(),
        options={CONF_EFFECT_SOURCE: EFFECT_SOURCE_RECOMMENDED},
    )

    await async_init_integration(hass, mock_config_entry)

    patch_aidot_client.class_mock.assert_called_once()
    assert patch_aidot_client.class_mock.call_args.kwargs["options"] == {
        CONF_EFFECT_SOURCE: EFFECT_SOURCE_RECOMMENDED
    }
