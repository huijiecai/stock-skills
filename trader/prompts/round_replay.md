【第 {rounds} 轮 · 模拟看盘 {date} {clock}】

## 开场(仅本会话第 1 轮做)
1. list_docs(doc_type='watch_replay', trade_date='{date}') 看该日已回放到第几轮
2. 若已有轮日志:get_doc 读最近 3 轮恢复状态(持仓/自设条件/待办),你是接续回放,不是从零开始
3. 若没有:正常开始。先读今日盘前预案 get_doc(doc_type='premarket', trade_date='{date}')(有则对照预案执行)

## 每轮流程
1. **核对触发线**:最近轮日志"自设条件与待办"里的 if-then 是否已满足(如"站上X价位""板块涨停归零")→ 满足即当场处理
2. 调 scan_market(mode='replay', date='{date}', time='{clock}') 快扫 → 按六类轮转判断(②B 发现走强→同轮触发③;已入库未持仓的 active 预期走强=③买点窗口评估)→ 输出。
注意:本轮回放模式,查行情和下单都要带回放参数——get_quotes 传 mode='replay', date='{date}', time='{clock}';
若交易,execute 也传 mode='replay', date='{date}', time='{clock}'(按当时价成交)。

## 轮日志(硬约束:不写完本轮不算结束)
每轮结束前必须 save_doc(doc_type='watch_replay', name='r{rounds}', trade_date='{date}'),content 为 md,首行 `# r{rounds} {clock}`,固定小节:

- **市况**:指数/主线/最强方向,一两行
- **持仓评估**:每只现价/浮盈/双出口结论(未触发也写"未触发")
- **行动**:做了什么/为什么不
- **自设条件与待办**:本轮给自己定的条件、在等的触发线、下轮要看什么(没有也明确写"无",不许省略小节)。**这些是下轮开场要核对的活触发线,不是写完就完**

**边界**:轮环节只许写 watch_replay 轮日志——close/premarket 等文档由专门流程负责,轮内禁写。
