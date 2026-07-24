import json
from pathlib import Path

from typer.testing import CliRunner

from trading_engine.cli import app


runner = CliRunner()


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    (tmp_path / "skills").mkdir()
    binary = tmp_path / "astock" / "build" / "astock"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\necho 'astock version test'\n", encoding="utf-8")
    binary.chmod(0o755)
    return tmp_path, binary


def test_version_option_does_not_require_a_command() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "trader 0.1.0"


def test_config_show_uses_explicit_repo_root(tmp_path: Path) -> None:
    repo_root, binary = _workspace(tmp_path)

    result = runner.invoke(
        app,
        ["config", "show"],
        env={"TRADER_REPO_ROOT": str(repo_root)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["repo_root"] == str(repo_root)
    assert payload["astock_binary"] == str(binary)


def test_astock_check_is_machine_readable(tmp_path: Path) -> None:
    repo_root, _ = _workspace(tmp_path)

    result = runner.invoke(
        app,
        ["astock", "check"],
        env={"TRADER_REPO_ROOT": str(repo_root)},
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["available"] is True
    assert payload["version"] == "astock version test"
