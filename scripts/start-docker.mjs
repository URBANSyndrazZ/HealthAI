#!/usr/bin/env node
import { spawn, spawnSync } from 'node:child_process';
import { copyFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const rootDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const backendEnv = join(rootDir, 'backend', '.env');
const backendEnvSample = join(rootDir, 'backend', '.env.sample');
const passthroughArgs = process.argv.slice(2);

if (!existsSync(backendEnv) && existsSync(backendEnvSample)) {
  copyFileSync(backendEnvSample, backendEnv);
  console.log('[HealthAI] created backend/.env from backend/.env.sample');
}

if (existsSync(backendEnv)) {
  console.log('[HealthAI] Tip: add your own DEEPSEEK_API_KEY and DASHSCOPE_API_KEY to backend/.env before using AI features.');
}

const check = spawnSync('docker', ['--version'], { encoding: 'utf8' });
if (check.status !== 0) {
  console.error('[HealthAI] Docker is required. Start Docker Desktop or install Docker Engine, then try again.');
  process.exit(1);
}

const child = spawn('docker', ['compose', 'up', '--build', ...passthroughArgs], {
  cwd: rootDir,
  stdio: 'inherit',
});

child.on('exit', (code, signal) => {
  process.exitCode = code === null && signal ? 1 : code;
});
