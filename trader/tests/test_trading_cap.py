"""单票 40% 上限:8/17 剑桥 57.6% 的回归测试。"""

import trader.store as store
from trader.tools.trading import _check_position_cap


def test_position_cap_blocks_and_allows():
    a = store.Account(schema="t_cap")
    a.reset()
    # 账户 10 万,买 4 万(40%)应放行
    assert _check_position_cap(a, "603083", 200, 200.0) is None  # 4.0万=40.0% 边界内
    # 买 5.8 万(58%)应拒绝,并给出最大可买数量
    a.buy("603083", 200, 200.0)  # 现持有 4 万
    msg = _check_position_cap(a, "603083", 100, 200.0)  # 再买 2 万 → 6万/10万超限
    assert msg and "超过单票上限 40%" in msg and "最多再买" in msg

