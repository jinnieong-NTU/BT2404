import os
import sys
import socket
import traceback

class LogStream:
    def __init__(self, filepath):
        self.f = open(filepath, "a", encoding="utf-8")
    def write(self, s):
        try:
            self.f.write(s)
            self.f.flush()
        except Exception:
            pass
    def flush(self):
        try:
            self.f.flush()
        except Exception:
            pass
    def isatty(self):
        return False

log_out = LogStream(os.path.join(os.path.dirname(__file__), "server_stdout.log"))
log_err = LogStream(os.path.join(os.path.dirname(__file__), "server_stderr.log"))

if sys.stdout is None or not hasattr(sys.stdout, "isatty"):
    sys.stdout = log_out
if sys.__stdout__ is None:
    sys.__stdout__ = log_out

if sys.stderr is None or not hasattr(sys.stderr, "isatty"):
    sys.stderr = log_err
if sys.__stderr__ is None:
    sys.__stderr__ = log_err

import io
if sys.stdin is None or not hasattr(sys.stdin, "isatty"):
    sys.stdin = io.StringIO("")
if sys.__stdin__ is None:
    sys.__stdin__ = io.StringIO("")

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

if __name__ == "__main__":
    try:
        import uvicorn
        from app.main import app

        # Create dual-stack sockets supporting BOTH IPv4 (127.0.0.1) and IPv6 (::1 / localhost)
        # Bind to both 8080 and 8000 so localhost works regardless of which port is opened
        sockets = []
        for port in (8080, 8000):
            bound = False
            for attempt in range(5):
                try:
                    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    try:
                        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                    except Exception:
                        pass
                    s.bind(("::", port))
                    s.listen(128)
                    sockets.append(s)
                    bound = True
                    break
                except Exception as ex:
                    # Try IPv4 fallback
                    try:
                        s4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s4.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        s4.bind(("127.0.0.1", port))
                        s4.listen(128)
                        sockets.append(s4)
                        bound = True
                        break
                    except Exception:
                        pass
                    import time
                    time.sleep(0.5)

            if not bound:
                print(f"Note: Could not bind port {port}", flush=True)

        if not sockets:
            raise RuntimeError("No ports available to bind!")

        print("=" * 60, flush=True)
        print("Optimization Solver Server is running on:", flush=True)
        for s in sockets:
            p = s.getsockname()[1]
            print(f"  -> http://localhost:{p}/", flush=True)
            print(f"  -> http://127.0.0.1:{p}/", flush=True)
        print("=" * 60, flush=True)

        config = uvicorn.Config(app, log_level="info", use_colors=False)
        server = uvicorn.Server(config)
        server.run(sockets=sockets)
    except BaseException as e:
        crash_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_crash.log")
        with open(crash_path, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
