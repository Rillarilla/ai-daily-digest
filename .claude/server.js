const http = require('http');
const fs = require('fs');
const path = require('path');
const port = process.env.PORT || 8877;
const root = path.join(__dirname, '..');
const server = http.createServer((req, res) => {
  const fp = path.join(root, req.url === '/' ? '/email_preview.html' : req.url);
  fs.readFile(fp, (err, data) => {
    if (err) { res.writeHead(404); res.end('Not found'); }
    else { res.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'}); res.end(data); }
  });
});
server.listen(port, '127.0.0.1', () => console.log(`Listening on ${port}`));
