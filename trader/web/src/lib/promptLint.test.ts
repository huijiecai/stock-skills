import { describe, expect, it } from 'vitest'
import { extractPlaceholders, unknownPlaceholders, substitute } from './promptLint'

describe('extractPlaceholders(占位符提取)', () => {
  it('提取 {name} 占位符并去重', () => {
    expect(extractPlaceholders('【{date}({weekday})】 上一日 {prev} 重复 {date}'))
      .toEqual(['date', 'weekday', 'prev'])
  })
  it('{{}} 转义不视为占位符(JSON 示例保护)', () => {
    expect(extractPlaceholders('示例 {{"code": "000001"}} 与 {date}'))
      .toEqual(['date'])
  })
  it('空占位/非标识符名不提取', () => {
    expect(extractPlaceholders('{} {1abc} {a-b}')).toEqual([])
  })
})

describe('unknownPlaceholders(lint)', () => {
  it('标出不在可用集中的占位符(手误场景)', () => {
    expect(unknownPlaceholders('{date} {dat} {weekday}', ['date', 'weekday']))
      .toEqual(['dat'])
  })
  it('全部已知 → 空', () => {
    expect(unknownPlaceholders('{date} {prev}', ['date', 'prev'])).toEqual([])
  })
})

describe('substitute(替换预览)', () => {
  it('有值替换,未覆盖保留原样', () => {
    expect(substitute('{date} {prev}', { date: '20260824' })).toBe('20260824 {prev}')
  })
  it('{{}} 转义段原样保留', () => {
    expect(substitute('{{name}} {date}', { date: 'X', name: 'Y' })).toBe('{{name}} X')
  })
})
