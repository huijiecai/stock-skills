【第 {rounds} 轮 · 模拟看盘 {date} {clock}】
先调 scan_market(mode='replay', date='{date}', time='{clock}') 快扫;若本轮还没读过今日盘前预案,先调 get_doc(doc_type='premarket', trade_date='{date}')(有则对照预案执行)。
注意:本轮回放模式,查行情和下单都要带回放参数——get_quotes 传 mode='replay', date='{date}', time='{clock}';若交易,execute 也传 mode='replay', date='{date}', time='{clock}'(按当时价成交)。然后判断。
