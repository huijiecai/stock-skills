【收盘评估与复盘 · {date}】

## 第一步:加载
- get_positions / get_trades:持仓与今日成交(含决策留痕)
- get_doc(doc_type='premarket', trade_date='{date}'):今日盘前预案(对照用;无则记"今日无预案")
- list_docs(doc_type='expectation'):全部预期当前状态
- get_indices(mode='replay', date='{date}') / get_market_summary(date='{date}'):今日收盘市况

## 第二步:预期逐个更新(每日必做)
对每条 active 预期逐一评估(已有预期的例行更新):
- get_watchlist_quotes(该预期的组名, mode='replay', date='{date}'):收盘池健康度 X/Y
- 四维:催化有新进展吗?资金面(池 X/Y 变化)?价格确认(创新高/破关键位)?阶段变化?
- 阶段/状态变化 → set_doc_meta(文档 id, meta 改 stage/status);内容变化 → save_doc 同键覆盖(只改有变的)
- 预期兑现(故事讲完)→ set_doc_meta 改 status=fulfilled;被证伪 → status=invalid + meta.invalid_reason 记原因
- 预期结束 → 池组改名 archived- 前缀或删成员(避免明日快览噪音)

## 第三步:收盘逐股扫描(新方向兜底,自下而上——概念板块排名会漏,只有逐只归因才看得全)
- get_limit_up(date='{date}'):涨停全部过一遍 → 逐只归因到方向:
  哪些归入已有预期(资金面确认)?哪些是**不在库的新方向**?
- get_top_amount(date='{date}', limit=20):成交额前 N 异动 → 是否隐含新预期
- 发现强势新方向不在库 → 核心判断"这个方向是不是比别的更值得关注?" → 是就完整研究
  (联网归因→save_doc 预期文档→save_watchlist 池)

## 第四步:交易复盘
- get_trades 逐笔:基于什么预期?三维确认了吗?决策依据成立吗?
- 对照盘前预案:if-then 执行了吗?没执行的——条件未触发(正常)还是错过(记录原因)?
- 今日无交易 → 预案条件为什么没触发,是否符合预期

## 第五步:合规自检(逐项过)
- [ ] 每笔交易对照了三维确认?
- [ ] 卖出基于预期逻辑而非价格?
- [ ] 加仓独立满足买点(非仅价格新高)?
- [ ] 盘中有新方向遗漏吗(对照第三步扫描结果 vs 盘中实际关注)?
- [ ] 决策留痕完整(每笔有理由+预期关联)?
- [ ] 纪律标尺:**赚钱违规=错误 / 亏钱合规=正确**

## 第六步:落库
完整报告(收盘市况/预期变化表/新方向发现/交易复盘/合规结论/明日关注)
→ save_doc(doc_type='close', trade_date='{date}')
有新教训 → 另存 save_doc(doc_type='note', name='lesson-{date}')
