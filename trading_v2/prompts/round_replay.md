【第 {rounds} 轮 · 模拟看盘 {date} {clock}】
先调 scan_market(mode='replay', date='{date}', time='{clock}') 快扫;若本轮还没读过今日盘前预案,先调 get_doc(doc_type='premarket', trade_date='{date}')(有则对照预案执行);然后判断。
