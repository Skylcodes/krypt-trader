import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TraderConfig } from '../shared/types';
import { migrateConfig } from '../electron/system/legacy-settings';

let userData = '';
vi.mock('electron', () => ({ app: { getPath: () => userData } }));

async function freshStore() {
  vi.resetModules();
  return import('../electron/system/settings-store');
}

describe('excludedMarketPrefixes defaults', () => {
  let defaults: TraderConfig;
  beforeEach(async () => {
    userData = mkdtempSync(join(tmpdir(), 'krypt-exclude-'));
    defaults = (await freshStore()).DEFAULT_CONFIG;
  });
  afterEach(() => rmSync(userData, { recursive: true, force: true }));

  it('ships the Sky default denylist', () => {
    expect(defaults.excludedMarketPrefixes).toEqual([
      'KXNBA', 'KXNCAAMB', 'KXBTCD', 'KXBTC',
    ]);
  });

  it('backfills the default list for settings that never saved the key', () => {
    const out = migrateConfig({ minWhaleUsd: 3000 }, defaults);
    expect(out.excludedMarketPrefixes).toEqual(defaults.excludedMarketPrefixes);
  });

  it('keeps an explicit empty list (no filtering)', () => {
    const out = migrateConfig({ excludedMarketPrefixes: [] }, defaults);
    expect(out.excludedMarketPrefixes).toEqual([]);
  });
});
