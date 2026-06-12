package tdx

import (
	"strings"

	"github.com/injoyai/tdx/protocol"
)

// CompanyInfo 从 F10 公司概况中提取的结构化信息。
type CompanyInfo struct {
	Industry string // 通达信研究行业（如 "食品饮料-酿酒"）
	Sector   string // 一级行业（如 "食品饮料"）
	Province string // 注册省份（从注册地址推断）
	Business string // 经营范围摘要
}

// GetCompanyInfo 获取一只股票的 F10 公司概况信息。
// 返回解析后的行业/地域等字段。失败不报错，返回空结构。
func (c *Client) GetCompanyInfo(market, code string) (*CompanyInfo, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}

	ex := exchangeOf(market)
	cats, err := cli.GetCompanyCategory(ex, code)
	if err != nil {
		return nil, err
	}

	// 找 "公司概况" 分类
	var target *protocol.CompanyCategory
	for i := range cats {
		if strings.Contains(cats[i].Name, "公司概况") {
			target = &cats[i]
			break
		}
	}
	if target == nil {
		return &CompanyInfo{}, nil
	}

	content, err := cli.GetCompanyContent(ex, code, target.Filename, target.Start, target.Length)
	if err != nil {
		return &CompanyInfo{}, nil
	}

	return parseCompanyInfo(content), nil
}

// parseCompanyInfo 从 F10 公司概况文本中提取关键字段。
func parseCompanyInfo(content string) *CompanyInfo {
	info := &CompanyInfo{}

	// 解析"通达信研究行业│食品饮料-酿酒"
	if v := extractField(content, "通达信研究行业"); v != "" {
		info.Industry = v
		// 分离一级行业
		if idx := strings.Index(v, "-"); idx > 0 {
			info.Sector = v[:idx]
		} else {
			info.Sector = v
		}
	}

	// 解析"注册地址│贵州省遵义市仁怀市茅台镇"
	if v := extractField(content, "注册地址"); v != "" {
		info.Province = extractProvince(v)
	}

	// 解析"经营范围│..."
	if v := extractField(content, "经营范围"); v != "" {
		// 截断过长的经营范围
		r := []rune(v)
		if len(r) > 100 {
			v = string(r[:100])
		}
		info.Business = v
	}

	return info
}

// extractField 从 F10 文本中提取 "│fieldName│value│" 格式的值。
// TDX F10 使用 │ 分隔表格列。
func extractField(content, fieldName string) string {
	idx := strings.Index(content, fieldName)
	if idx < 0 {
		return ""
	}
	// 找到字段名后，往后找 │
	rest := content[idx+len(fieldName):]
	// 跳过空格和 │
	rest = strings.TrimLeft(rest, " \t│")
	// 取到下一个 │ 或 换行
	end := strings.IndexAny(rest, "│\n┤├")
	if end < 0 {
		end = len(rest)
	}
	return strings.TrimSpace(rest[:end])
}

// extractProvince 从地址字符串提取省份名称。
func extractProvince(addr string) string {
	provinces := []string{
		"北京", "天津", "上海", "重庆",
		"河北", "山西", "辽宁", "吉林", "黑龙江",
		"江苏", "浙江", "安徽", "福建", "江西", "山东",
		"河南", "湖北", "湖南", "广东", "广西", "海南",
		"四川", "贵州", "云南", "西藏",
		"陕西", "甘肃", "青海", "宁夏", "新疆", "内蒙古",
		"深圳", "大连", "青岛", "宁波", "厦门", // 计划单列市
	}
	for _, p := range provinces {
		if strings.Contains(addr, p) {
			return p
		}
	}
	// 兜底：取前两个字
	r := []rune(addr)
	if len(r) >= 2 {
		return string(r[:2])
	}
	return ""
}
