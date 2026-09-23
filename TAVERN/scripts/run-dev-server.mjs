import { spawn } from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const isWin = process.platform === 'win32';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tavRoot = path.resolve(__dirname, '..');

// Ensure common bun/node paths are in process.env.PATH
const extraPaths = [
  path.join(os.homedir(), '.bun', 'bin'),
  isWin ? path.join(process.env.LOCALAPPDATA || '', 'Programs', 'bun') : '/usr/local/bin',
  isWin ? path.join(process.env.USERPROFILE || '', '.bun', 'bin') : '',
];
for (const p of extraPaths) {
  if (p && fs.existsSync(p) && !process.env.PATH.includes(p)) {
    process.env.PATH = p + path.delimiter + process.env.PATH;
  }
}

function tryBun() {
  try {
    const check = spawn(isWin ? 'bun.exe' : 'bun', ['--version'], { stdio: 'ignore' });
    check.on('error', () => runNode());
    check.on('close', (code) => {
      if (code === 0) {
        runBun();
      } else {
        runNode();
      }
    });
  } catch {
    runNode();
  }
}

function runBun() {
  const p = spawn(isWin ? 'bun.cmd' : 'bun', ['--watch', 'server/index.ts'], {
    stdio: 'inherit',
    shell: isWin,
    cwd: tavRoot,
  });
  p.on('exit', (c) => process.exit(c || 0));
}

function runNode() {
  const tsxCli = path.join(tavRoot, 'node_modules', 'tsx', 'dist', 'cli.mjs');
  const [major, minor] = (process.versions.node || '22.0.0').split('.').map(Number);
  const sqliteFlag = (major === 22 && minor >= 5) || major > 22 ? ['--experimental-sqlite'] : [];

  let args = [];
  let execPath = process.execPath;
  if (fs.existsSync(tsxCli)) {
    args = [...sqliteFlag, tsxCli, 'watch', 'server/index.ts'];
  } else {
    execPath = isWin ? 'npx.cmd' : 'npx';
    args = ['tsx', 'watch', ...sqliteFlag, 'server/index.ts'];
  }

  const p = spawn(execPath, args, {
    stdio: 'inherit',
    shell: isWin && !fs.existsSync(tsxCli),
    cwd: tavRoot,
  });
  p.on('exit', (c) => process.exit(c || 0));
}

tryBun();
