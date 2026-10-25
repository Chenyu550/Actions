'use strict';

// Run with the built node.exe, both in CI and manually on Windows 7 SP1.
// This uses only built-in modules and loopback networking.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const dns = require('node:dns').promises;
const fs = require('node:fs');
const https = require('node:https');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { once } = require('node:events');
const { Worker } = require('node:worker_threads');

const watchdog = setTimeout(() => {
  console.error('FAIL: smoke test exceeded 60 seconds');
  process.exit(1);
}, 60_000);
watchdog.unref();

async function main() {
  console.log(JSON.stringify({ executable: process.execPath, version: process.version,
    platform: process.platform, arch: process.arch, os: os.release(), versions: process.versions }, null, 2));
  assert.match(process.version, /^v24\./);
  if (process.platform === 'win32') assert.equal(process.arch, 'x64');
  assert.ok(os.hostname().length > 0);
  assert.equal(typeof process.title, 'string');
  assert.ok(Date.now() > 1_600_000_000_000);
  const start = process.hrtime.bigint();
  await new Promise(resolve => setTimeout(resolve, 25));
  assert.ok(process.hrtime.bigint() > start);
  assert.ok(process.report.getReport().header.osName);
  assert.ok(new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai' }).format(new Date()));
  console.log('PASS hostname, process title, clocks, diagnostics, Intl');

  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'node24-win7-'));
  try {
    const filename = path.join(directory, '\u4e2d\u6587.txt');
    fs.writeFileSync(filename, 'Win7 \u4e2d\u6587', 'utf8');
    assert.equal(await fs.promises.readFile(filename, 'utf8'), 'Win7 \u4e2d\u6587');
    const copied = path.join(directory, 'copy.txt');
    fs.copyFileSync(filename, copied);
    assert.equal(fs.readFileSync(copied, 'utf8'), 'Win7 \u4e2d\u6587');
    const output = execFileSync(process.execPath, ['-e', 'console.log(process.argv[1])', '\u4e2d\u6587'], { encoding: 'utf8' });
    assert.equal(output.trim(), '\u4e2d\u6587');
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
  console.log('PASS filesystem, Unicode paths/arguments, child_process');

  const worker = new Worker(`
    const { parentPort } = require('node:worker_threads');
    const shared = new Int32Array(new SharedArrayBuffer(4));
    if (Atomics.wait(shared, 0, 0, 5) !== 'timed-out') throw Error('Atomics.wait');
    parentPort.postMessage(42);
  `, { eval: true });
  try {
    const [[answer], [exitCode]] = await Promise.all([
      once(worker, 'message'), once(worker, 'exit'),
    ]);
    assert.equal(answer, 42);
    assert.equal(exitCode, 0);
  } finally {
    await worker.terminate();
  }
  assert.ok((await dns.lookup('localhost')).address);
  console.log('PASS worker_threads, Atomics.wait, localhost DNS');

  assert.equal(crypto.randomBytes(32).length, 32);
  assert.equal(crypto.createHash('sha256').update('abc').digest('hex'),
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
  const message = Buffer.from('Windows 7');
  assert.ok(crypto.verify(null, message, publicKey, crypto.sign(null, message, privateKey)));

  const fixtures = fs.existsSync(path.join(__dirname, 'fixtures'))
    ? path.join(__dirname, 'fixtures') : path.join(__dirname, '../tests/fixtures');
  const server = https.createServer({
    key: fs.readFileSync(path.join(fixtures, 'localhost-key.pem')),
    cert: fs.readFileSync(path.join(fixtures, 'localhost-cert.pem')),
  }, (_request, response) => response.end('TLS OK'));
  server.listen(0, '127.0.0.1');
  try {
    await once(server, 'listening');
    const body = await new Promise((resolve, reject) => {
      const request = https.get({ hostname: '127.0.0.1', port: server.address().port,
        // This fixture is a public, self-signed test certificate.
        rejectUnauthorized: false, agent: false }, response => {
        let text = '';
        response.setEncoding('utf8');
        response.on('data', chunk => { text += chunk; });
        response.on('end', () => resolve(text));
        response.on('error', reject);
      });
      request.on('error', reject);
      request.setTimeout(10_000, () => request.destroy(new Error('TLS loopback timeout')));
    });
    assert.equal(body, 'TLS OK');
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
  console.log('PASS crypto, TLS/HTTPS over loopback');

  const { DatabaseSync } = require('node:sqlite');
  const db = new DatabaseSync(':memory:');
  try {
    db.exec('CREATE TABLE test (value INTEGER); INSERT INTO test VALUES (42)');
    assert.equal(db.prepare('SELECT value FROM test').get().value, 42);
  } finally {
    db.close();
  }
  console.log('PASS node:sqlite');
  console.log('All smoke tests passed on this machine.');
}

main().then(() => clearTimeout(watchdog), error => {
  console.error(error);
  process.exit(1);
});
