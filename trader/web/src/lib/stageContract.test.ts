import { describe, expect, it } from 'vitest'
import { nextStageId } from './stageContract'

describe('nextStageId', () => {
  it('uses a readable ASCII label when possible', () => {
    expect(nextStageId({}, 'Market Observe')).toBe('market-observe')
  })

  it('hides the internal identifier for Chinese labels', () => {
    expect(nextStageId({}, '盘中观察')).toBe('stage')
    expect(nextStageId({ stage: {}, 'stage-2': {} }, '盘后复盘')).toBe('stage-3')
  })

  it('returns a unique stable identifier', () => {
    expect(nextStageId({ observe: {} }, 'observe')).toBe('observe-2')
  })
})
