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
    # The build creates one control DB plus five attached schema files. Point
    # Datasette at every attached file so the complete logical model is browsable.
    schema_names = ("etl", "intake", "omop", "naaccr", "sdc")
    datasette_url = "https://lite.datasette.io/" + "".join(
        f"{'?' if index == 0 else '&'}url=http://localhost:8000/sdc_cdm.{schema}.db"
        for index, schema in enumerate(schema_names)
    )
    print(f"Try {datasette_url} for a friendlier GUI into the databases")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        httpd.shutdown()
        httpd.server_close()
