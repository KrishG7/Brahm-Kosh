"""
Local Web Server for Brahm-Kosh 3D Interface.

Provides a REST API to serve the codebase graph directly to a 3D frontend.
"""

import json
import os
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

from brahm_kosh.models import Project
from brahm_kosh.analysis.architect import analyze_structure
from brahm_kosh.analysis.narrator import generate_narration


class ProjectGraphServer:
    def __init__(self, project: Project, port: int = 8080):
        self.project = project
        self.port = port
        self.frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
        
        # Ensure frontend directory exists
        os.makedirs(self.frontend_dir, exist_ok=True)
        
        # Generate the graph payload once
        self.graph_data = self._generate_graph_payload(project)
        self.architecture_data = analyze_structure(project)

    def _generate_graph_payload(self, project: Project) -> dict:
        """
        Translates the deep hierarchical Project into a flat node/link JSON payload
        suitable for 3D force graph libraries.
        """
        nodes = []
        links = []
        folders_tracked = set()
        
        files = project.all_files()
        
        for fm in files:
            # Add file node
            nodes.append({
                "id": fm.relative_path,
                "name": fm.name,
                "type": "file",
                "parent": os.path.dirname(fm.relative_path) or "root",
                "val": fm.complexity + 1,
                "heat": fm.heat_label,
                "purpose": fm.purpose,
                "language": fm.language,
                "symbols": [s.name for s in fm.symbols],
                "narration": generate_narration(fm)
            })
            
            # Forward dependencies become links (edges) of type 'dependency'
            for dep in fm.dependencies:
                links.append({
                    "source": fm.relative_path,
                    "target": dep,
                    "type": "dependency"
                })
                
            # Track and inject folders
            parts = fm.relative_path.split('/')
            current_path = ""
            for i in range(len(parts) - 1): # Exclude the file name itself
                folder_name = parts[i]
                parent_path = current_path
                current_path = f"{current_path}/{folder_name}" if current_path else folder_name
                
                if current_path not in folders_tracked:
                    folders_tracked.add(current_path)
                    nodes.append({
                        "id": current_path,
                        "name": folder_name,
                        "type": "folder",
                        "parent": parent_path or "root",
                        "val": 15, # Fixed large size for folders
                        "heat": "Low"
                    })
                    
                # Add structural edge from parent to current
                links.append({
                    "source": parent_path or "root",
                    "target": current_path,
                    "type": "structural"
                })
                
            # Add structural edge from containing folder to the file
            parent_dir = os.path.dirname(fm.relative_path)
            links.append({
                "source": parent_dir or "root",
                "target": fm.relative_path,
                "type": "structural"
            })
            
        # Add a special Root node if it doesn't exist
        nodes.append({
            "id": "root",
            "name": project.name or "Repository",
            "type": "folder",
            "parent": None,
            "val": 20,
            "heat": "Optimal"
        })

        return {"nodes": nodes, "links": links}

    def start(self):
        # Create handler correctly scoped with data
        graph_data = self.graph_data
        arch_data = self.architecture_data
        frontend_dir = self.frontend_dir
        
        class APIHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=frontend_dir, **kwargs)
                
            def do_GET(self):
                parsed_path = urlparse(self.path).path
                
                if parsed_path == "/api/graph":
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps(graph_data).encode())
                    return
                    
                if parsed_path == "/api/architecture":
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps(arch_data).encode())
                    return

                # Normal file serving (e.g. index.html)
                return super().do_GET()
                
            def log_message(self, format, *args):
                # Suppress annoying HTTP request logs to keep CLI clean
                pass

        server_address = ('', self.port)
        httpd = HTTPServer(server_address, APIHandler)
        
        url = f"http://localhost:{self.port}"
        print(f"\n🚀 Brahm-Kosh 3D Server running!")
        print(f"👉 Open {url} in your browser.")
        print(f"📡 API Endpoints:")
        print(f"   - {url}/api/graph")
        print(f"   - {url}/api/architecture")
        print(f"\nPress Ctrl+C to stop the server...\n")
        
        # Open browser automatically
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.server_close()


def serve_project(project: Project, port: int = 8080):
    server = ProjectGraphServer(project, port)
    server.start()
