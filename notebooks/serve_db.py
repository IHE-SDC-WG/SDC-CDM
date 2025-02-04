#!/usr/bin/env python3
import http.server
import socketserver

PORT = 8000
DIRECTORY = "./public"


class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
    print(f"Serving directory '{DIRECTORY}' at http://localhost:{PORT}")
    print(f"Try https://lite.datasette.io/?url=http://localhost:8000/sdc_cdm.db for a friendlier GUI into the database")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        httpd.shutdown()
        httpd.server_close()
