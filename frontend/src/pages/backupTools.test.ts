// Backups in two groups (14 Nov): "Can replace anything" and "Only if your own pick runs out".
import { describe, expect, it } from 'vitest'
import { onlyIfSaying, onlyReplaces, type BackupLine } from './backupTools.ts'

const line = (id: number, name: string, item: string): BackupLine => ({ variety: { id, name }, itemKey: `Food/${item}` })

const BRAN = line(1, 'Bran flakes', 'Cereal')
const CORN = line(2, 'Corn flakes', 'Cereal')
const OATS = line(3, 'Oats', 'Cereal')
const RICE = line(4, 'White rice', 'Rice')
const OIL = line(5, 'Sunflower oil', 'Oil')
const LINES = [BRAN, CORN, OATS, RICE, OIL]

describe('onlyReplaces', () => {
  it('says a second variety of a chosen item only replaces that pick', () => {
    expect(onlyReplaces(CORN, LINES, { 1: 1, 5: 1 }, 1)).toEqual(['Bran flakes'])
  })

  it('says food of an item not chosen can replace anything', () => {
    expect(onlyReplaces(RICE, LINES, { 1: 1, 5: 1 }, 1)).toEqual([])
  })

  it('says anything while there is still room for more of that item', () => {
    // Two cereals allowed, one chosen: Corn flakes can fill any gap.
    expect(onlyReplaces(CORN, LINES, { 1: 1 }, 2)).toEqual([])
  })

  it('names every chosen variety of the item once the item is full', () => {
    expect(onlyReplaces(OATS, LINES, { 1: 1, 2: 1 }, 2)).toEqual(['Bran flakes', 'Corn flakes'])
  })

  it('counts more than one of the same variety', () => {
    expect(onlyReplaces(CORN, LINES, { 1: 2 }, 2)).toEqual(['Bran flakes'])
  })
})

describe('onlyIfSaying', () => {
  it('reads as plain words', () => {
    expect(onlyIfSaying(['Bran flakes'])).toBe('only if your Bran flakes runs out')
    expect(onlyIfSaying(['Bran flakes', 'Corn flakes'])).toBe('only if your Bran flakes or Corn flakes runs out')
  })
})
