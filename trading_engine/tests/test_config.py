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
    assert settings.astock_binary == tmp_path / "astock" / "build" / "astock"
    assert settings.data_dir == tmp_path / "trading_engine" / "data"
