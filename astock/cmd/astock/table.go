package main

import (
	"fmt"
	"strings"

	"github.com/mattn/go-runewidth"
)

// table 是一个 CJK 宽度感知的简易表格打印器。
// 使用方式:
//
//	t := newTable("日期", 12, "开盘", 8, "收盘", 8)
//	t.Row("2026-06-12", "217.55", "217.55")
//	t.Print()
type table struct {
	cols []col
	rows [][]string
}

type col struct {
	header string
	width  int
}

// newTable 接收 (header, width) 交替参数。
func newTable(args ...any) *table {
	t := &table{}
	for i := 0; i+1 < len(args); i += 2 {
		h, _ := args[i].(string)
		w, _ := args[i+1].(int)
		t.cols = append(t.cols, col{header: h, width: w})
	}
	return t
}

// Row 添加一行数据。
func (t *table) Row(cells ...string) {
	t.rows = append(t.rows, cells)
}

// Print 输出表头 + 分隔线 + 全部行。
func (t *table) Print() {
	// 表头：第一列左对齐，其余右对齐（和数据一致）
	var hdr strings.Builder
	var sep strings.Builder
	for i, c := range t.cols {
		if i > 0 {
			hdr.WriteString("  ")
			sep.WriteString("  ")
		}
		if i == 0 {
			hdr.WriteString(padRight(c.header, c.width))
		} else {
			hdr.WriteString(padLeft(c.header, c.width))
		}
		sep.WriteString(strings.Repeat("-", c.width))
	}
	fmt.Println(hdr.String())
	fmt.Println(sep.String())

	// 数据行
	for _, row := range t.rows {
		var line strings.Builder
		for i, c := range t.cols {
			if i > 0 {
				line.WriteString("  ")
			}
			cell := ""
			if i < len(row) {
				cell = row[i]
			}
			if i == 0 {
				line.WriteString(padRight(cell, c.width))
			} else {
				line.WriteString(padLeft(cell, c.width))
			}
		}
		fmt.Println(line.String())
	}
}

// padRight 左对齐填充到指定显示宽度。
func padRight(s string, width int) string {
	sw := runewidth.StringWidth(s)
	if sw >= width {
		return s
	}
	return s + strings.Repeat(" ", width-sw)
}

// padLeft 右对齐填充到指定显示宽度。
func padLeft(s string, width int) string {
	sw := runewidth.StringWidth(s)
	if sw >= width {
		return s
	}
	return strings.Repeat(" ", width-sw) + s
}
