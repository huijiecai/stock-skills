from pathlib import Path

from trading_engine.config import TraderSettings


def test_settings_resolve_workspace_paths(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TRADER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("TRADER_ASTOCK_BINARY", raising=False)
    monkeypatch.delenv("TRADER_DATA_DIR", raising=False)

    settings = TraderSettings.load()

    assert settings.repo_root == tmp_path
    assert settings.astock_binary == tmp_path / "astock" / "astock"
    assert settings.data_dir == tmp_path / "trading_engine" / "data"


def test_settings_do_not_fall_back_to_unverified_legacy_binary(
    tmp_path: Path, monkeypatch
) -> None:
    current_binary = tmp_path / "astock" / "astock"
    legacy_binary = tmp_path / "astock" / "build" / "astock"
    legacy_binary.parent.mkdir(parents=True)
    legacy_binary.touch()
    monkeypatch.setenv("TRADER_REPO_ROOT", str(tmp_path))
    monkeypatch.delenv("TRADER_ASTOCK_BINARY", raising=False)

    settings = TraderSettings.load()

    assert settings.astock_binary == current_binary
    assert settings.astock_binary.exists() is False
