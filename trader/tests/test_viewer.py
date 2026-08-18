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


def test_doc_pages():
    """盘前/盘后文档页:8/17 有 close,8/18 有 premarket(今晚跑的)。"""
    r = client.get("/doc/close/20260817")
    assert r.status_code == 200 and "盘后总结" in r.text
    r = client.get("/doc/premarket/20260818")
    assert r.status_code == 200 and "盘前预案" in r.text
    # 日视图应带文档入口
    r = client.get("/day/20260817")
    assert "盘后总结" in r.text and "/doc/close/20260817" in r.text
    # 白名单外 404
    assert client.get("/doc/transcript_live/20260817").status_code == 404


def test_prompt_pages():
    """prompt 版本库页面:列表/历史/全文/diff。"""
    r = client.get("/prompts")
    assert r.status_code == 200 and "system" in r.text and "round_live" in r.text
    r = client.get("/prompt/system")
    assert r.status_code == 200 and "v1" in r.text
    r = client.get("/prompt/system/1")
    assert r.status_code == 200 and "买入决策" in r.text
    r = client.get("/prompt/system/diff/1/1")
    assert r.status_code == 200  # 同版 diff 也应 200(无变更)


def test_compare_page():
    """对比页:两场 + 血统校验(冒烟2 自比 + 两 live 场)。"""
    r = client.get("/compare?runs=1,2")   # 两场 live(回填)
    assert r.status_code == 200 and "血统校验" in r.text and "指标对比" in r.text
    r = client.get("/compare?runs=4")     # 只选一场 → 400
    assert r.status_code == 400
