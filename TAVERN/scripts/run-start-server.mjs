import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const isWin = process.platform === 'win32';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tavRoot = path.resolve(__dirname, '..');

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
  const p = spawn(isWin ? 'bun.cmd' : 'bun', ['server/index.ts'], {
    stdio: 'inherit',
    shell: isWin,
    cwd: tavRoot,
  });
  p.on('exit', (c) => process.exit(c || 0));
}

function runNode() {
  const p = spawn('node', ['--experimental-sqlite', 'server/index.ts'], {
    stdio: 'inherit',
    shell: isWin,
    cwd: tavRoot,
  });
  p.on('exit', (c) => process.exit(c || 0));
}

tryBun();
