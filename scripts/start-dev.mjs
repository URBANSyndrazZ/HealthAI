#!/usr/bin/env node
import { spawn, spawnSync } from 'node:child_process';
import { copyFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const args = new Set(process.argv.slice(2));

if (args.has('--help') || args.has('-h')) {
  console.log(`Usage: npm run dev [options]

Options:
  --backend-only    Start only the FastAPI backend
  --frontend-only   Start only the Vite frontend
  --skip-install    Reuse existing dependencies without installing them
  -h, --help        Show this help
`);
  process.exit(0);
}

const skipInstall = args.has('--skip-install');
const backendOnly = args.has('--backend-only');
const frontendOnly = args.has('--frontend-only');
const rootDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const backendDir = join(rootDir, 'backend');
const frontendDir = join(rootDir, 'frontend');
const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';

function copyEnvIfMissing(source, target) {
  if (!existsSync(target) && existsSync(source)) {
    copyFileSync(source, target);
    console.log(`[HealthAI] created ${target.replace(rootDir, '.')}`);
  }
}

function checkCommand(command, args = ['--version']) {
  const result = spawnSync(command, args, { encoding: 'utf8' });
  return result.status === 0;
}

function requireCommand(command, help) {
  if (!checkCommand(command)) {
    throw new Error(`${command} is required. ${help}`);
  }
}

function runSync(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: 'inherit', ...options });
  if (result.status !== 0) {
    throw new Error(`Command failed with exit code ${result.status}: ${command} ${args.join(' ')}`);
  }
}

function prepareBackend() {
  copyEnvIfMissing(join(backendDir, '.env.sample'), join(backendDir, '.env'));

  const venvDir = join(backendDir, '.venv');
  const venvPython = process.platform === 'win32'
    ? join(venvDir, 'Scripts', 'python.exe')
    : join(venvDir, 'bin', 'python');

  if (!existsSync(venvPython)) {
    const pythonCommand = process.platform === 'win32' ? 'python' : 'python3';
    requireCommand(pythonCommand, 'Install Python 3.11 or later.');
    console.log('[HealthAI] creating backend virtual environment...');
    runSync(pythonCommand, ['-m', 'venv', '.venv'], { cwd: backendDir });
  }

  if (!skipInstall) {
    console.log('[HealthAI] installing backend dependencies...');
    runSync(venvPython, ['-m', 'pip', 'install', '-r', 'requirements.txt'], { cwd: backendDir });
  }

  return venvPython;
}

function prepareFrontend() {
  copyEnvIfMissing(join(frontendDir, '.env.sample'), join(frontendDir, '.env'));
  requireCommand(npmCommand, 'Install Node.js 20.19+, 22+, or a compatible LTS version.');

  if (!skipInstall && !existsSync(join(frontendDir, 'node_modules'))) {
    console.log('[HealthAI] installing frontend dependencies...');
    runSync(npmCommand, ['install'], { cwd: frontendDir });
  }
}

function startProcess(label, command, args, options) {
  const child = spawn(command, args, { stdio: 'inherit', ...options });
  child.healthaiLabel = label;
  return child;
}

const children = [];
const exits = [];

function shutdown(signal = 'SIGTERM') {
  for (const child of children) {
    if (child.exitCode === null && child.signalCode === null) {
      child.kill(signal);
    }
  }
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

try {
  requireCommand('node');

  if (!backendOnly) {
    prepareFrontend();
  }

  if (!frontendOnly) {
    const backendPython = prepareBackend();
    const backend = startProcess('backend', backendPython, [
      '-m', 'uvicorn', 'app.main:app', '--reload', '--host', '0.0.0.0', '--port', '8000',
    ], { cwd: backendDir });
    children.push(backend);
    exits.push(new Promise((resolve) => backend.once('exit', (code, signal) => resolve({ label: 'backend', code, signal }))));
  }

  if (!backendOnly) {
    const frontend = startProcess('frontend', npmCommand, ['run', 'dev'], { cwd: frontendDir });
    children.push(frontend);
    exits.push(new Promise((resolve) => frontend.once('exit', (code, signal) => resolve({ label: 'frontend', code, signal }))));
  }

  const firstExit = await Promise.race(exits);
  console.log(`[HealthAI] ${firstExit.label} exited; stopping the other process...`);
  shutdown();

  const results = await Promise.all(exits);
  const failed = results.find(({ code }) => code !== 0 && code !== null);
  process.exitCode = failed ? (failed.code || 1) : 0;
} catch (error) {
  console.error(`[HealthAI] ${error.message}`);
  shutdown();
  process.exitCode = 1;
}

