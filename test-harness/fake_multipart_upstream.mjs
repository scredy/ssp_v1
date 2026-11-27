import { createServer } from 'node:http';

const server = createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const body = Buffer.concat(chunks);
  if (request.method === 'GET' && request.url === '/api/cars/') {
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end('[]');
    return;
  }
  const result = {
    method: request.method,
    path: request.url,
    contentType: request.headers['content-type'] ?? '',
    bodyBytes: body.length,
    hasPhotoField: body.includes(Buffer.from('name="photos"')),
    hasFilename: body.includes(Buffer.from('filename="proxy-check.png"')),
  };
  response.writeHead(200, { 'content-type': 'application/json' });
  response.end(JSON.stringify(result));
});

server.listen(8111, '127.0.0.1', () => process.stdout.write('Fake multipart upstream listening on 127.0.0.1:8111\n'));
