"""Property-based tests for configuration validation.

**Validates: Requirements 17.3**
"""

import json
import tempfile
from pathlib import Path
from hypothesis import given, strategies as st, settings
import pytest

from config import Config, ConfigError


# Strategy for valid LLM providers
valid_llm_providers = st.sampled_from(["claude", "openai"])

# Strategy for valid configuration
@st.composite
def valid_config(draw):
    """Generate a valid configuration."""
    return {
        "trigger_words": draw(st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=20)),
        "llm_provider": draw(valid_llm_providers),
        "join_delay_min": draw(st.integers(min_value=60, max_value=3600)),
        "join_delay_max": draw(st.integers(min_value=60, max_value=3600)),
        "daily_join_limit": draw(st.integers(min_value=1, max_value=50)),
        "llm_max_concurrent": draw(st.integers(min_value=1, max_value=100)),
        "llm_timeout": draw(st.integers(min_value=1, max_value=300)),
        "llm_max_retries": draw(st.integers(min_value=1, max_value=10)),
        "health_check_interval": draw(st.integers(min_value=1, max_value=3600)),
        "spam_cache_update_interval": draw(st.integers(min_value=1, max_value=3600)),
        "max_spam_examples": draw(st.integers(min_value=1, max_value=100))
    }


# Strategy for invalid configurations (missing required fields)
@st.composite
def config_missing_fields(draw):
    """Generate configuration with missing required fields."""
    required_fields = [
        "trigger_words",
        "llm_provider",
        "join_delay_min",
        "join_delay_max",
        "daily_join_limit",
        "llm_max_concurrent",
        "llm_timeout",
        "llm_max_retries",
        "health_check_interval",
        "spam_cache_update_interval",
        "max_spam_examples"
    ]
    
    # Remove at least one required field
    fields_to_include = draw(st.lists(
        st.sampled_from(required_fields),
        min_size=0,
        max_size=len(required_fields) - 1,
        unique=True
    ))
    
    config = {}
    for field in fields_to_include:
        if field == "trigger_words":
            config[field] = draw(st.lists(st.text(min_size=1), min_size=1))
        elif field == "llm_provider":
            config[field] = draw(valid_llm_providers)
        else:
            config[field] = draw(st.integers(min_value=1, max_value=3600))
    
    return config


# Strategy for invalid configurations (invalid values)
@st.composite
def config_invalid_values(draw):
    """Generate configuration with invalid values."""
    config = draw(valid_config())
    
    # Choose which field to make invalid
    invalid_field = draw(st.sampled_from([
        "trigger_words_not_list",
        "llm_provider_invalid",
        "join_delay_min_out_of_range",
        "join_delay_max_out_of_range",
        "join_delay_min_greater_than_max",
        "daily_join_limit_out_of_range",
        "llm_max_concurrent_invalid"
    ]))
    
    if invalid_field == "trigger_words_not_list":
        config["trigger_words"] = "not a list"
    elif invalid_field == "llm_provider_invalid":
        config["llm_provider"] = draw(st.text().filter(lambda x: x not in ["claude", "openai"]))
    elif invalid_field == "join_delay_min_out_of_range":
        config["join_delay_min"] = draw(st.one_of(
            st.integers(max_value=59),
            st.integers(min_value=3601)
        ))
    elif invalid_field == "join_delay_max_out_of_range":
        config["join_delay_max"] = draw(st.one_of(
            st.integers(max_value=59),
            st.integers(min_value=3601)
        ))
    elif invalid_field == "join_delay_min_greater_than_max":
        config["join_delay_min"] = draw(st.integers(min_value=1000, max_value=3600))
        config["join_delay_max"] = draw(st.integers(min_value=60, max_value=999))
    elif invalid_field == "daily_join_limit_out_of_range":
        config["daily_join_limit"] = draw(st.one_of(
            st.integers(max_value=0),
            st.integers(min_value=51)
        ))
    elif invalid_field == "llm_max_concurrent_invalid":
        config["llm_max_concurrent"] = draw(st.integers(max_value=0))
    
    return config


@settings(max_examples=100)
@given(config_data=config_missing_fields())
def test_property_33_missing_fields(config_data):
    """Property 33: Invalid Configuration Raises Error (Missing Fields)
    
    **Validates: Requirements 17.3**
    
    For any configuration file with missing required fields,
    loading it must raise a validation error.
    """
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name
    
    try:
        # Attempt to load config should raise ConfigError
        with pytest.raises(ConfigError) as exc_info:
            Config(temp_path)
        
        # Verify error message mentions missing fields
        assert "Missing required configuration fields" in str(exc_info.value)
    finally:
        # Cleanup
        Path(temp_path).unlink()


@settings(max_examples=100)
@given(config_data=config_invalid_values())
def test_property_33_invalid_values(config_data):
    """Property 33: Invalid Configuration Raises Error (Invalid Values)
    
    **Validates: Requirements 17.3**
    
    For any configuration file with invalid values,
    loading it must raise a validation error.
    """
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name
    
    try:
        # Attempt to load config should raise ConfigError
        with pytest.raises(ConfigError):
            Config(temp_path)
    finally:
        # Cleanup
        Path(temp_path).unlink()


@settings(max_examples=50)
@given(config_data=valid_config())
def test_property_33_valid_config_loads(config_data):
    """Property 33: Valid Configuration Loads Successfully
    
    **Validates: Requirements 17.3**
    
    For any configuration file with all required fields and valid values,
    loading it must succeed without raising an error.
    """
    # Ensure join_delay_min <= join_delay_max
    if config_data["join_delay_min"] > config_data["join_delay_max"]:
        config_data["join_delay_min"], config_data["join_delay_max"] = \
            config_data["join_delay_max"], config_data["join_delay_min"]
    
    # Create temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name
    
    try:
        # Loading should succeed
        config = Config(temp_path)
        
        # Verify all fields are accessible
        assert config["trigger_words"] == config_data["trigger_words"]
        assert config["llm_provider"] == config_data["llm_provider"]
        assert config["join_delay_min"] == config_data["join_delay_min"]
        assert config["join_delay_max"] == config_data["join_delay_max"]
        assert config["daily_join_limit"] == config_data["daily_join_limit"]
    finally:
        # Cleanup
        Path(temp_path).unlink()


def test_property_33_missing_file():
    """Property 33: Missing Configuration File Raises Error
    
    **Validates: Requirements 17.3**
    
    When configuration file does not exist, loading must raise an error.
    """
    with pytest.raises(ConfigError) as exc_info:
        Config("nonexistent_config.json")
    
    assert "Configuration file not found" in str(exc_info.value)


def test_property_33_invalid_json():
    """Property 33: Invalid JSON Raises Error
    
    **Validates: Requirements 17.3**
    
    When configuration file contains invalid JSON, loading must raise an error.
    """
    # Create temporary file with invalid JSON
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{ invalid json }")
        temp_path = f.name
    
    try:
        with pytest.raises(ConfigError) as exc_info:
            Config(temp_path)
        
        assert "Invalid JSON" in str(exc_info.value)
    finally:
        Path(temp_path).unlink()
