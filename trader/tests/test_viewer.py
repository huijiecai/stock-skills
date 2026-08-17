"""viewer 冒烟:页面 200 + 关键内容(只读,用真实库)。"""

from fastapi.testclient import TestClient

from trader.viewer.app import app

client = TestClient(app)


def test_index_redirect():
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/day/" in r.headers["location"]


def test_day_20260817():
    """8/17 有 r1-r11 轮日志 + 2 笔交易,是现成的验收数据。"""
    r = client.get("/day/20260817")
    assert r.status_code == 200
    assert "r11" in r.text and "r1" in r.text          # 时间线
    assert "剑桥科技" in r.text                          # 交易
    assert "预期面板" in r.text


def test_round_detail():
    r = client.get("/round/20260817/1")
    assert r.status_code == 200
    assert "轮日志" in r.text
    assert "没有思考流落盘" in r.text                    # r1 早于落盘机制,应优雅降级


def test_trades():
    r = client.get("/trades/20260817")
    assert r.status_code == 200
    assert "决策留痕" in r.text and "登海种业" in r.text


def test_expectations():
    r = client.get("/expectations")
    assert r.status_code == 200
    assert "种业" in r.text and "CPO" in r.text


def test_steps_parser():
    """消息流拍平:user-prompt/tool-call/tool-return/text 各成一步。"""
    from trader.viewer.app import _steps
    fake = {"messages": [{"parts": [
        {"part_kind": "user-prompt", "content": "第 1 轮"},
        {"part_kind": "tool-call", "tool_name": "scan_market", "args": {}},
        {"part_kind": "tool-return", "tool_name": "scan_market", "content": "【指数】..."},
        {"part_kind": "text", "content": "判断:持有"},
    ]}]}
    steps = _steps(fake)
    assert [s["kind"] for s in steps] == ["prompt", "call", "ret", "text"]
    assert "scan_market" in steps[1]["title"]
