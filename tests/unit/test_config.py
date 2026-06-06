from pathlib import Path

from app.core.config import Settings


def test_settings_env_file_uses_project_root_absolute_path():
    env_file = Path(Settings.model_config["env_file"])

    assert env_file.is_absolute()
    assert env_file.name == ".env"
    assert env_file.parent.name == "sales-agent"
