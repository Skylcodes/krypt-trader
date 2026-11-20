import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

export const __dirname = dirname(fileURLToPath(import.meta.url));
export const ROOT = dirname(__dirname);
export const PY_DIR = join(ROOT, 'python');
export const VENV = join(PY_DIR, '.venv');
export const VENV_PY = process.platform === 'win32'
  ? join(VENV, 'Scripts', 'python.exe')
  : join(VENV, 'bin', 'python');

const isWin = process.platform === 'win32';

export function run(cmd, args, opts = {}) {
  const display = `${cmd} ${args.map((a) => (a.includes(' ') ? `"${a}"` : a)).join(' ')}`;
  console.log(`> ${display}`);
  const r = spawnSync(cmd, args, {
    stdio: 'inherit',
    cwd: PY_DIR,
    shell: false,
    ...opts,
  });
  if (r.error) {
    throw new Error(`${cmd} could not be spawned: ${r.error.message}`);
  }
  if (r.status !== 0) {
    throw new Error(`${display} failed with exit code ${r.status}`);
  }
}

export function tryCmd(cmd, args) {
  try {
    const r = spawnSync(cmd, args, {
      stdio: 'ignore',
      shell: false,
      windowsHide: true,
    });
    return !r.error && r.status === 0;
  } catch {
    return false;
  }
}

/**
 * Prefer the interpreter that CI/setup-python put first on PATH (`python` /
 * `python3`). The Windows `py -3` launcher tracks the newest install and can
 * resolve to a free-threaded (abi3t / python3t.dll) build that cryptography
 * wheels depend on — those fail PyInstaller selftest. Pin to 3.11 via the
 * launcher only as a last resort.
 */
function pythonLooksUsable(cmd, prefixArgs = []) {
  // Reject free-threaded (abi3t) builds — cryptography's win_amd64 abi3t
  // wheel depends on python3t.dll and fails the frozen-backend selftest.
  const r = spawnSync(
    cmd,
    [
      ...prefixArgs,
      '-c',
      "import sys,sysconfig; "
      + "v=sys.version_info; assert v.major==3 and 10<=v.minor<=13; "
      + "assert not (sysconfig.get_config_var('Py_GIL_DISABLED') or 0); "
      + "print(sys.version)",
    ],
    { encoding: 'utf8', windowsHide: true },
  );
  return !r.error && r.status === 0;
}

let _systemPy = null;
let _systemPyPrefix = [];
export function findSystemPython() {
  if (_systemPy) return _systemPy;
  const candidates = isWin
    ? [
        { cmd: 'python', args: [], spawnAs: 'python' },
        { cmd: 'python3', args: [], spawnAs: 'python3' },
        { cmd: 'py', args: ['-3.11'], spawnAs: 'py', prefix: ['-3.11'] },
        { cmd: 'py', args: ['-3.12'], spawnAs: 'py', prefix: ['-3.12'] },
        { cmd: 'py', args: ['-3.10'], spawnAs: 'py', prefix: ['-3.10'] },
        { cmd: 'py', args: ['-3'], spawnAs: 'py', prefix: ['-3'] },
      ]
    : [
        { cmd: 'python3', args: [], spawnAs: 'python3' },
        { cmd: 'python', args: [], spawnAs: 'python' },
      ];
  for (const c of candidates) {
    const prefix = c.prefix || [];
    if (!tryCmd(c.cmd, [...prefix, '--version'])) continue;
    if (!pythonLooksUsable(c.cmd, prefix)) {
      console.log(`>> Skipping ${c.cmd} ${prefix.join(' ')} (not a standard CPython 3.10–3.13)`);
      continue;
    }
    _systemPy = c.spawnAs;
    _systemPyPrefix = prefix;
    return _systemPy;
  }
  throw new Error(
    'No usable Python 3.10–3.13 interpreter found on PATH '
    + '(free-threaded / experimental builds are skipped). '
    + 'Install Python 3.11+ from https://python.org and try again.',
  );
}

export function systemPyPrefix() {
  findSystemPython();
  return _systemPyPrefix;
}

export function ensureVenv({ force = false } = {}) {
  if (!existsSync(VENV) || force) {
    const sys = findSystemPython();
    console.log('>> Creating Python venv at python/.venv');
    run(sys, [...systemPyPrefix(), '-m', 'venv', '.venv']);
  }
  if (!existsSync(VENV_PY)) {
    throw new Error(`venv created but no interpreter at ${VENV_PY}`);
  }
  if (!force && tryCmd(VENV_PY, ['-c', 'import httpx, cryptography, websockets'])) {
    return;
  }
  console.log('>> Installing Python deps into venv (one-time, ~30s)');
  run(VENV_PY, ['-m', 'pip', 'install', '--upgrade', 'pip', 'wheel', '--disable-pip-version-check']);
  run(VENV_PY, ['-m', 'pip', 'install', '-r', 'requirements.txt', '--disable-pip-version-check']);
}
