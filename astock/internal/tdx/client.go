// Package tdx 是 injoyai/tdx 的薄封装层。
// 用法：tdx.New() 返回 *Client，使用完毕后 Close()。
//
// 注意：injoyai/tdx 的 DialWith(nil) 会因 dial 函数为空而失败，必须用 DialDefault()。
package tdx

import (
	"fmt"
	"sync"

	itdx "github.com/injoyai/tdx"
)

// Client 是单连接 TDX 客户端的薄封装。
// 内部惰性连接：第一次调用 raw() 时才真正 Dial，便于命令未触达 TDX 时也能正常运行。
type Client struct {
	mu  sync.Mutex
	cli *itdx.Client
}

// New 返回一个未连接的 Client；首次调用 Raw() 才会真正建连。
func New() *Client {
	return &Client{}
}

// Raw 返回底层 *itdx.Client，必要时建立连接。
func (c *Client) Raw() (*itdx.Client, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.cli != nil {
		return c.cli, nil
	}
	// WithDebug(false) 关闭 TDX 库内部日志，避免打到 stdout 污染输出
	cli, err := itdx.DialDefault(itdx.WithDebug(false))
	if err != nil {
		return nil, fmt.Errorf("tdx dial: %w", err)
	}
	c.cli = cli
	return c.cli, nil
}

// Close 关闭底层连接（如已建立）。
func (c *Client) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.cli == nil {
		return nil
	}
	c.cli.Close()
	c.cli = nil
	return nil
}
