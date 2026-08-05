package tdx

import (
	"encoding/binary"
	"fmt"
	"math"
	"strings"

	"github.com/injoyai/ios"
	iosclient "github.com/injoyai/ios/client"
	"github.com/injoyai/tdx/protocol"
)

const marketRankType uint16 = 0x054B

const (
	marketCategorySH  uint16 = 0
	marketCategorySZ  uint16 = 2
	marketCategoryAll uint16 = 6
	marketCategoryBJ  uint16 = 12
)

const (
	marketSortNone uint16 = 0
	marketSortDesc uint16 = 1
	marketSortAsc  uint16 = 2
)

var marketSortTypes = map[string]uint16{
	"code":            0x00,
	"price":           0x06,
	"volume":          0x09,
	"amount":          0x0A,
	"change":          0x0E,
	"amplitude":       0x0F,
	"pe":              0x11,
	"entrust-ratio":   0x12,
	"inout-ratio":     0x15,
	"locked-ratio":    0x1B,
	"locked-amount":   0x1C,
	"open-amount":     0x1D,
	"volume-ratio":    0x23,
	"turnover":        0x24,
	"float-cap":       0x26,
	"total-cap":       0x27,
	"strength":        0x2D,
	"speed":           0x2E,
	"activity":        0x2F,
	"short-turnover":  0xCC,
	"volume-speed":    0xD0,
	"main-net-amount": 0xD4,
	"amount-2m":       0x10C,
}

// MarketRankRequest describes one server-side sorted page of A-share quotes.
type MarketRankRequest struct {
	Market string
	Sort   string
	Order  string
	Offset int
	Limit  int
}

// MarketRankItem is one row returned by TDX's 0x054B sorted quote interface.
type MarketRankItem struct {
	Market        string  `json:"market"`
	Code          string  `json:"code"`
	Price         float64 `json:"price"`
	PreClose      float64 `json:"pre_close"`
	Open          float64 `json:"open"`
	High          float64 `json:"high"`
	Low           float64 `json:"low"`
	ChangePct     float64 `json:"change_pct"`
	AmplitudePct  float64 `json:"amplitude_pct"`
	Volume        int64   `json:"volume"`
	CurrentVolume int64   `json:"current_volume"`
	Amount        float64 `json:"amount"`
	InVolume      int64   `json:"in_volume"`
	OutVolume     int64   `json:"out_volume"`
	RiseSpeed     float64 `json:"rise_speed"`
	Active        uint16  `json:"active"`
}

type marketRankResponse struct {
	items []MarketRankItem
	err   error
}

// GetMarketRank asks TDX to sort the full selected market and return one page.
// The upstream library does not decode 0x054B yet, so this method temporarily
// intercepts only that response type while delegating all others unchanged.
func (c *Client) GetMarketRank(req MarketRankRequest) ([]MarketRankItem, error) {
	category, err := marketRankCategory(req.Market)
	if err != nil {
		return nil, err
	}
	sortType, ok := marketSortTypes[strings.ToLower(req.Sort)]
	if !ok {
		return nil, fmt.Errorf("不支持的排序字段 %q", req.Sort)
	}
	if req.Offset < 0 || req.Offset > math.MaxUint16 {
		return nil, fmt.Errorf("offset 必须在 0-%d 之间", math.MaxUint16)
	}
	if req.Limit < 1 || req.Limit > 100 {
		return nil, fmt.Errorf("limit 必须在 1-100 之间")
	}

	order := marketSortDesc
	switch strings.ToLower(req.Order) {
	case "desc":
	case "asc":
		order = marketSortAsc
	default:
		return nil, fmt.Errorf("order 只能是 desc 或 asc")
	}
	if sortType == marketSortTypes["code"] {
		order = marketSortNone
	}

	body := make([]byte, 18)
	binary.LittleEndian.PutUint16(body[0:2], category)
	binary.LittleEndian.PutUint16(body[2:4], sortType)
	binary.LittleEndian.PutUint16(body[4:6], uint16(req.Offset))
	binary.LittleEndian.PutUint16(body[6:8], uint16(req.Limit))
	binary.LittleEndian.PutUint16(body[8:10], order)
	binary.LittleEndian.PutUint16(body[10:12], 5)
	binary.LittleEndian.PutUint16(body[14:16], 1)

	c.rankMu.Lock()
	defer c.rankMu.Unlock()

	raw, err := c.Raw()
	if err != nil {
		return nil, err
	}
	previousHandler := raw.Event.OnDealMessage
	raw.Event.OnDealMessage = func(conn *iosclient.Client, msg ios.Acker) {
		response, decodeErr := protocol.Decode(msg.Payload())
		if decodeErr == nil && response.Type == marketRankType {
			items, itemErr := decodeMarketRank(response.Data)
			raw.Wait.Done(fmt.Sprint(response.MsgID), marketRankResponse{items: items, err: itemErr})
			return
		}
		previousHandler(conn, msg)
	}
	defer func() { raw.Event.OnDealMessage = previousHandler }()

	result, err := raw.SendFrame(&protocol.Frame{
		Control: protocol.Control01,
		Type:    marketRankType,
		Data:    body,
	})
	if err != nil {
		return nil, fmt.Errorf("TDX 市场排行请求失败: %w", err)
	}
	response, ok := result.(marketRankResponse)
	if !ok {
		return nil, fmt.Errorf("TDX 市场排行返回类型异常: %T", result)
	}
	if response.err != nil {
		return nil, response.err
	}
	return response.items, nil
}

func marketRankCategory(market string) (uint16, error) {
	switch strings.ToLower(market) {
	case "all":
		return marketCategoryAll, nil
	case "sh":
		return marketCategorySH, nil
	case "sz":
		return marketCategorySZ, nil
	case "bj":
		return marketCategoryBJ, nil
	default:
		return 0, fmt.Errorf("market 只能是 all、sh、sz 或 bj")
	}
}

func decodeMarketRank(body []byte) ([]MarketRankItem, error) {
	if len(body) < 4 {
		return nil, fmt.Errorf("TDX 市场排行响应过短: %d", len(body))
	}
	count := int(binary.LittleEndian.Uint16(body[2:4]))
	body = body[4:]
	items := make([]MarketRankItem, 0, count)

	for i := 0; i < count; i++ {
		if len(body) < 9 {
			return nil, fmt.Errorf("TDX 市场排行第 %d 行头部不完整", i+1)
		}
		market := marketRankMarketName(body[0])
		code := strings.TrimRight(string(body[1:7]), "\x00 ")
		active := binary.LittleEndian.Uint16(body[7:9])
		body = body[9:]

		values := make([]int64, 17)
		var err error
		for j := 0; j < 9; j++ {
			body, values[j], err = cutMarketRankValue(body)
			if err != nil {
				return nil, fmt.Errorf("TDX 市场排行第 %d 行字段 %d: %w", i+1, j+1, err)
			}
		}
		if len(body) < 4 {
			return nil, fmt.Errorf("TDX 市场排行第 %d 行成交额不完整", i+1)
		}
		amount := float64(math.Float32frombits(binary.LittleEndian.Uint32(body[:4])))
		body = body[4:]
		for j := 9; j < 17; j++ {
			body, values[j], err = cutMarketRankValue(body)
			if err != nil {
				return nil, fmt.Errorf("TDX 市场排行第 %d 行字段 %d: %w", i+1, j+1, err)
			}
		}
		if len(body) < 56 {
			return nil, fmt.Errorf("TDX 市场排行第 %d 行尾部不完整", i+1)
		}
		riseSpeed := float64(int16(binary.LittleEndian.Uint16(body[2:4]))) / 100
		body = body[56:]

		price := float64(values[0]) / 100
		preClose := float64(values[0]+values[1]) / 100
		changePct := 0.0
		amplitudePct := 0.0
		if preClose > 0 {
			changePct = (price - preClose) / preClose * 100
			amplitudePct = float64(values[3]-values[4]) / 100 / preClose * 100
		}
		items = append(items, MarketRankItem{
			Market: market, Code: code, Price: price, PreClose: preClose,
			Open:      float64(values[0]+values[2]) / 100,
			High:      float64(values[0]+values[3]) / 100,
			Low:       float64(values[0]+values[4]) / 100,
			ChangePct: changePct, AmplitudePct: amplitudePct,
			Volume: values[7], CurrentVolume: values[8], Amount: amount,
			InVolume: values[9], OutVolume: values[10], RiseSpeed: riseSpeed, Active: active,
		})
	}
	return items, nil
}

func cutMarketRankValue(data []byte) ([]byte, int64, error) {
	for i, b := range data {
		if b&0x80 != 0 {
			continue
		}
		encoded := data[:i+1]
		value := int64(encoded[0] & 0x3F)
		for j := 1; j < len(encoded); j++ {
			value += int64(encoded[j]&0x7F) << uint(6+(j-1)*7)
		}
		if encoded[0]&0x40 != 0 {
			value = -value
		}
		return data[i+1:], value, nil
	}
	return nil, 0, fmt.Errorf("变长整数不完整")
}

func marketRankMarketName(market byte) string {
	switch market {
	case 0:
		return "SZ"
	case 1:
		return "SH"
	case 2:
		return "BJ"
	default:
		return fmt.Sprintf("%d", market)
	}
}
