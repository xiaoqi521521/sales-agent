import tomllib
from pathlib import Path


def test_mysql_async_driver_declares_cryptography_for_sha2_auth():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]

    assert any(item.split(">=", 1)[0] == "cryptography" for item in dependencies)
