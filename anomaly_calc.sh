#!/bin/bash
# ============================================================================
# 异动计算器 - 计算10日100%和30日200%异动触发价
# 用法:
#   ./anomaly_calc.sh <代码>              # 明日模式(默认): 用今日收盘，假设明日指数不变
#   ./anomaly_calc.sh <代码> --live       # 实时模式: 自动获取实时股价，指数用今日收盘估算
#   ./anomaly_calc.sh <代码> --price 20.50 --idx 4130.25  # 手动指定当前价
#
# 已验证与开盘啦完全一致（3只股票含除权除息场景）
# ============================================================================
#
# 【监管公式】
# N日涨幅偏离值 = (期末收盘价/期初参考价 - 1)×100% - (指数期末/指数期初 - 1)×100%
# 期初参考价 = 不复权收盘价 - 期间累计每股分红
# 触发价 = 期初参考价 × (1 + (阈值 + 指数涨幅)/100)，假设明天指数不变
# 阈值: 10日→100%, 30日→200%
#
# 【坑1: 基准指数】
#   深市→深证综指(399106)  ← 不是深证成指(399001)！差5%+
#   沪市→上证指数(000001)
#   创业板→创业板指(399006)
#   科创板→科创50(000688)
#
# 【坑2: 必须不复权】
#   股票数据用 --adjust none，不能用默认的 --adjust qfq(前复权)
#   前复权会调整除权日之前的历史价格，导致偏离值计算错误
#   正确做法: 不复权收盘价 - 期间累计每股分红(从起始日到今天的每股派息之和)
#   无除权除息的股票: 不复权=前复权，结果不受影响
#
# 【坑3: N日窗口内取最大偏离日】
#   不能固定用窗口第一天作为参考！
#   必须遍历窗口内所有起始日，取偏离值最大的那个
#   原因: 股票最低点可能在窗口中间而非第一天
#   窗口范围: 30日→28个交易日前到1交易日前; 10日→8个交易日前到1交易日前
#
# 【坑4: XDXR派息列号】
#   astock query xdxr 输出列: $1=日期 $2=类型 $3=送股 $4=转增 $5=派息 $6=配股价 $7=配股比
#   派息是$5！不是$4($4是转增，通常为0)！每股派息 = $5/10
#
# 【坑5: awk语法】
#   - function必须定义在END块外部（macOS awk在END内定义function会报syntax error）
#   - close是awk保留字，不能用作变量名
#   - 数组索引用计数器(sn++/xn++)，不要直接用NR偏移，否则数据行数不对齐时会出空值
# ============================================================================

ASTOCK="./astock/astock"

# --- 解析参数 ---
LIVE=0
MANUAL_PRICE=""
MANUAL_IDX=""
CODE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --live) LIVE=1; shift ;;
        --price) MANUAL_PRICE="$2"; shift 2 ;;
        --idx)   MANUAL_IDX="$2"; shift 2 ;;
        *) CODE="$1"; shift ;;
    esac
done

if [ -z "$CODE" ]; then
    echo "用法: $0 <股票代码> [--live] [--price X --idx Y]"
    echo "示例:"
    echo "  $0 000636                    # 明日模式(默认)"
    echo "  $0 000636 --live              # 实时模式(自动获取实时股价)"
    echo "  $0 000636 --price 80.5 --idx 4130  # 手动指定当前价"
    exit 1
fi

case "$CODE" in
    68*) IDX="000688"; IDX_NAME="科创50" ;;
    6*)  IDX="000001"; IDX_NAME="上证指数" ;;
    0*)  IDX="399106"; IDX_NAME="深证综指" ;;
    3*)  IDX="399006"; IDX_NAME="创业板指" ;;
    *)   echo "❌ 不支持的代码段: ${CODE:0:2}"; exit 1 ;;
esac

# --- 确定模式 ---
if [ "$LIVE" -eq 1 ] || [ -n "$MANUAL_PRICE" ] || [ -n "$MANUAL_IDX" ]; then
    MODE="live"
else
    MODE="tomorrow"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$MODE" = "live" ]; then
    echo " 📊 异动计算器 | $CODE | 基准: $IDX_NAME | 实时模式"
else
    echo " 📊 异动计算器 | $CODE | 基准: $IDX_NAME | 明日模式"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo -n "  获取数据..."
STOCK_TMP=$(mktemp)
IDX_TMP=$(mktemp)
XDXR_TMP=$(mktemp)
trap "rm -f $STOCK_TMP $IDX_TMP $XDXR_TMP" EXIT

# 不复权数据 + 指数数据 + 除权除息记录
$ASTOCK query kline "$CODE" --limit 31 --adjust none > "$STOCK_TMP" 2>/dev/null
$ASTOCK query kline "$IDX" --type index --limit 31 > "$IDX_TMP" 2>/dev/null
$ASTOCK query xdxr "$CODE" > "$XDXR_TMP" 2>/dev/null

S_N=$(awk 'NR>2{n++}END{print n+0}' "$STOCK_TMP")
I_N=$(awk 'NR>2{n++}END{print n+0}' "$IDX_TMP")

if [ "$S_N" -lt 30 ] || [ "$I_N" -lt 30 ]; then
    echo " ❌ 数据不足(股票:${S_N}条 指数:${I_N}条)"
    exit 1
fi
echo " ✅ 股票${S_N}条 指数${I_N}条"

# --- 获取实时价格(如果需要) ---
LIVE_S=""
LIVE_I=""

if [ "$MODE" = "live" ]; then
    if [ -n "$MANUAL_PRICE" ]; then
        LIVE_S="$MANUAL_PRICE"
        echo "  📈 手动指定股价: ${LIVE_S}元"
    else
        LIVE_S=$($ASTOCK live quote "$CODE" --json 2>/dev/null | grep -o '"price": [0-9.]*' | head -1 | awk '{print $2}')
        if [ -z "$LIVE_S" ] || [ "$LIVE_S" = "0" ]; then
            echo "  ⚠️  无法获取实时股价，回退到今日收盘"
        else
            echo "  📈 实时股价: ${LIVE_S}元"
        fi
    fi

    if [ -n "$MANUAL_IDX" ]; then
        LIVE_I="$MANUAL_IDX"
        echo "  📊 手动指定指数: ${LIVE_I}"
    else
        echo "  💡 指数用今日收盘估算(可用 --idx 手动指定实时指数)"
    fi
fi

# 提取XDXR: 格式 "date per_share_dividend" (每股派息 = 每10股派息/10)
XDXR_LIST=$(awk 'NR>2 && $5>0{printf "%s,%.4f;", $1, $5/10}' "$XDXR_TMP")

awk -v xdxr_list="$XDXR_LIST" -v live_s="$LIVE_S" -v live_i="$LIVE_I" -v idx_name="$IDX_NAME" '
NR==FNR && FNR>2 { sn++; sc[sn]=$5; sd[sn]=$1; next }
NR!=FNR && FNR>2 { xn++; xc[xn]=$5 }

function cum_div(start_date, j, sum) {
    sum = 0
    for (j = 1; j <= nx; j++) {
        if (length(xd[j]) > 0 && xd[j] > start_date && xd[j] <= today) {
            sum += dv[j]
        }
    }
    return sum
}

END {
    today = sd[sn]

    # 确定当前价格: 实时模式用手动/实时价格，否则用今日收盘
    if (live_s != "" && live_s+0 > 0) {
        sT = live_s+0
        is_live = 1
    } else {
        sT = sc[sn]
        is_live = 0
    }
    if (live_i != "" && live_i+0 > 0) {
        iT = live_i+0
    } else {
        iT = xc[xn]
    }

    printf "\n  日期: %s | 当前价: %.2f元 | %s: %.2f\n\n", today, sT, idx_name, iT

    # 解析XDXR列表
    nx = split(xdxr_list, xarr, ";")
    for (j = 1; j <= nx; j++) {
        if (length(xarr[j]) > 0) {
            split(xarr[j], parts, ",")
            xd[j] = parts[1]
            dv[j] = parts[2]+0
        }
    }

    # --- 10日偏离: 在10日窗口内找最大偏离 ---
    best10_dev = -9999
    for (i = sn - 8; i <= sn - 1; i++) {
        if (i < 1) continue
        cd = cum_div(sd[i])
        ref = sc[i] - cd
        sr = (sT / ref - 1) * 100
        ir = (iT / xc[i] - 1) * 100
        dev = sr - ir
        if (dev > best10_dev) {
            best10_dev = dev
            best10_i = i
            best10_cd = cd
            best10_ref = ref
            best10_ir = ir
        }
    }
    s10 = best10_ref
    i10 = xc[best10_i]
    d10 = sd[best10_i]
    sr10 = (sT / s10 - 1) * 100
    ir10 = (iT / i10 - 1) * 100
    dev10 = best10_dev
    rem10 = 100 - dev10

    printf "  ┌── 10日偏离 → 100%%异动 ──────────────────┐\n"
    printf "  │  期初参考: %.2f (%s)  最大偏离日      │\n", s10, d10
    if (best10_cd > 0) {
        printf "  │  不复权: %.2f  分红扣减: %.2f            │\n", sc[best10_i], best10_cd
    }
    printf "  │  个股涨幅: %+.2f%%  指数涨幅: %+.2f%%      │\n", sr10, ir10
    printf "  │  偏离值: %+.2f%%                        │\n", dev10
    printf "  │  剩余额度: %.2f%%                        │\n", rem10
    if (dev10 >= 100) {
        printf "  │  ⚠️  已触发100%%异动!                    │\n"
    } else {
        up10 = s10 * (1 + (100 + ir10) / 100)
        up10_pct = (up10 / sT - 1) * 100
        printf "  │  上触: 需涨%.2f%% → %.2f元              │\n", up10_pct, up10
    }
    printf "  └──────────────────────────────────────────┘\n"

    # --- 30日偏离: 在30日窗口内找最大偏离 ---
    best30_dev = -9999
    for (i = sn - 28; i <= sn - 1; i++) {
        if (i < 1) continue
        cd = cum_div(sd[i])
        ref = sc[i] - cd
        sr = (sT / ref - 1) * 100
        ir = (iT / xc[i] - 1) * 100
        dev = sr - ir
        if (dev > best30_dev) {
            best30_dev = dev
            best30_i = i
            best30_cd = cd
            best30_ref = ref
            best30_ir = ir
        }
    }
    s30 = best30_ref
    i30 = xc[best30_i]
    d30 = sd[best30_i]
    sr30 = (sT / s30 - 1) * 100
    ir30 = (iT / i30 - 1) * 100
    dev30 = best30_dev
    rem30 = 200 - dev30

    printf "\n  ┌── 30日偏离 → 200%%异动 ──────────────────┐\n"
    printf "  │  期初参考: %.2f (%s)  最大偏离日      │\n", s30, d30
    if (best30_cd > 0) {
        printf "  │  不复权: %.2f  分红扣减: %.2f            │\n", sc[best30_i], best30_cd
    }
    printf "  │  个股涨幅: %+.2f%%  指数涨幅: %+.2f%%      │\n", sr30, ir30
    printf "  │  偏离值: %+.2f%%                        │\n", dev30
    printf "  │  剩余额度: %.2f%%                        │\n", rem30
    if (dev30 >= 200) {
        printf "  │  ⚠️  已触发200%%异动!                    │\n"
    } else {
        up30 = s30 * (1 + (200 + ir30) / 100)
        up30_pct = (up30 / sT - 1) * 100
        printf "  │  上触: 需涨%.2f%% → %.2f元              │\n", up30_pct, up30
    }
    printf "  └──────────────────────────────────────────┘\n"

    printf "\n  💡 触发价假设指数不变(=当前值)\n"
    if (is_live) {
        printf "  💡 实时模式: 指数实时变化可用 --idx 指定\n"
    } else {
        printf "  💡 明日模式: 用 --live 切换实时计算\n"
    }
    printf "  💡 不复权价-期间分红 | N日窗口内取最大偏离\n"
}
' "$STOCK_TMP" "$IDX_TMP"
