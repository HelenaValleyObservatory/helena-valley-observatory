#!/usr/bin/env python3
import os, socket, time
from datetime import datetime, timezone

OUTDIR = "/mnt/SYSTEM_ARCHIVE/OBSERVATORY/data/beast_raw"
HOST, PORT = "127.0.0.1", 30002

os.makedirs(OUTDIR, exist_ok=True)

def day_str():
    return datetime.now(timezone.utc).strftime("%Y%m%d")

def ts_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def open_out(day):
    path = os.path.join(OUTDIR, f"beast_{day}.txt")
    return open(path, "a", buffering=1)

def main():
    cur_day = day_str()
    out = open_out(cur_day)

    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((HOST, PORT))
            sock.settimeout(30)

            buf = b""
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        raise RuntimeError("EOF from readsb beast port")
                    buf += chunk

                    # AVR frames are like: *8D....;
                    # We'll split on ';' and reconstruct frames.
                    while b";" in buf:
                        part, buf = buf.split(b";", 1)
                        line = part.strip()
                        if not line:
                            continue
                        if not line.startswith(b"*"):
                            continue
                        frame = (line + b";").decode("utf-8", errors="ignore")
                        now_day = day_str()
                        if now_day != cur_day:
                            out.close()
                            cur_day = now_day
                            out = open_out(cur_day)
                        out.write(f"{ts_str()} {frame}\n")

                except socket.timeout:
                    continue

        except Exception as e:
            try:
                sock.close()
            except Exception:
                pass
            time.sleep(2)

if __name__ == "__main__":
    main()
