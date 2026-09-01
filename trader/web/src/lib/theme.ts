/** antd 主题对接 :root token(T3.1)::root 是唯一真相源,此处启动时读取喂给
 *  ConfigProvider——antd 组件主色/圆角/字体与自定义 CSS 保持同一套体系,
 *  不再出现默认蓝 #1677ff。jsdom(测试)取不到时回退字面量。 */
import type { ThemeConfig } from 'antd'

const root = typeof document !== 'undefined'
  ? getComputedStyle(document.documentElement) : null

function v(name: string, fallback: string): string {
  return (root?.getPropertyValue(name) || fallback).trim()
}

export const themeConfig: ThemeConfig = {
  token: {
    colorPrimary: v('--accent', '#175cd3'),
    colorLink: v('--accent', '#175cd3'),
    colorSuccess: v('--down', '#027a48'),   // 操作成功绿(与 A 股跌绿同值,语义各表)
    colorError: v('--danger', '#cf1322'),
    colorWarning: v('--warn', '#b54708'),
    borderRadius: Number(v('--radius-sm', '8px').replace('px', '')),
    fontFamily: v('--font-ui', "-apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif"),
  },
}
