import json
from pathlib import Path

from pd_agent.benchmark import BenchmarkConfig


CONFIG_PATH = Path("benchmarks/configs/openai-official-gpt-5.6-luna-brain-on.json")


def test_official_openai_config_freezes_output_limit_and_public_settings() -> None:
    config = BenchmarkConfig.from_dict(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))

    assert config.provider == "openai"
    assert config.model == "gpt-5.6-luna"
    assert config.brain_enabled is True
    assert config.model_config["max_output_tokens"] == 16_384
    assert config.model_config["reasoning"] == {"effort": "medium"}
    assert config.model_config["service_tier"] == "default"
    assert config.model_config["store"] is False


def test_output_limit_is_part_of_config_identity() -> None:
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config = BenchmarkConfig.from_dict(raw)
    changed = dict(raw)
    changed["model_config"] = dict(raw["model_config"])
    changed["model_config"]["max_output_tokens"] = 32_768

    assert config.config_hash() != BenchmarkConfig.from_dict(changed).config_hash()
