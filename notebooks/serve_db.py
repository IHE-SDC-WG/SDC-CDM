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
    # The three-schema layout produces one control DB plus three attached schema
    # files (sdc_cdm.omop.db / sdc_cdm.naaccr.db / sdc_cdm.sdc.db). Point Datasette
    # at each attached file so all three logical schemas are browsable.
    datasette_url = (
        "https://lite.datasette.io/"
        "?url=http://localhost:8000/sdc_cdm.omop.db"
        "&url=http://localhost:8000/sdc_cdm.naaccr.db"
        "&url=http://localhost:8000/sdc_cdm.sdc.db"
    )
    print(f"Try {datasette_url} for a friendlier GUI into the databases")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        httpd.shutdown()
        httpd.server_close()
