import http.server
import socketserver
import json

class TestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = json.dumps({"status": "ok", "service": "test_server"})
        self.wfile.write(response.encode())
    
    def do_POST(self):
        self.do_GET()

PORT = 8080
with socketserver.TCPServer(("", PORT), TestHandler) as httpd:
    print(f"Test server running on port {PORT}")
    httpd.serve_forever()
