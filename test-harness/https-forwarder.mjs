import https from 'node:https';
import http from 'node:http';
import { readFileSync } from 'node:fs';

const [listenPort, upstreamPort, pfxPath, passphrase] = process.argv.slice(2);
if (!listenPort || !upstreamPort || !pfxPath || !passphrase) {
  throw new Error('Usage: https-forwarder.mjs <listen-port> <upstream-port> <pfx-path> <passphrase>');
}

https.createServer({ pfx: readFileSync(pfxPath), passphrase }, (request, response) => {
  const chunks = [];
  request.on('data', (chunk) => chunks.push(chunk));
  request.on('end', () => {
    // Django's development server does not implement chunked uploads. Buffer
    // only inside this local test terminator and send a normal content length.
    const body = Buffer.concat(chunks);
    const headers = { ...request.headers, host: `localhost:${upstreamPort}`, 'x-forwarded-proto': 'https' };
    delete headers['transfer-encoding'];
    headers['content-length'] = String(body.length);
    const upstream = http.request({ hostname: '127.0.0.1', port: Number(upstreamPort), path: request.url, method: request.method, headers }, (upstreamResponse) => {
      response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
      upstreamResponse.pipe(response);
    });
    upstream.on('error', () => {
      if (!response.headersSent) response.writeHead(502, { 'cache-control': 'no-store' });
      response.end('Test upstream unavailable.');
    });
    upstream.end(body);
  });
}).listen(Number(listenPort), '127.0.0.1');
