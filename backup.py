"""Backup dan restore database KasirWarung.

Pakai: python backup.py             # backup (ter-enkripsi .dump.enc)
       python backup.py restore <file.dump[.enc]> <nama_db_tujuan>
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "backups")
OFFSITE_FILE = os.path.join(BASE, "offsite_path.txt")
KEYFILE = os.path.join(BASE, "secret.key")
SUFFIX = ".dump.enc"
KEEP = 7
KONEKSI = ["-h", "127.0.0.1", "-p", "5432", "-U", "kasir"]


def jalankan(args):
    with open(os.path.join(BASE, "db_password.txt")) as f:
        env = dict(os.environ, PGPASSWORD=f.read().strip())
    subprocess.run(args, check=True, text=True, capture_output=True, env=env)


def amankan(path, mode):
    os.chmod(path, mode)


def enkripsi(plain, enc):
    subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-in", plain,
         "-out", enc, "-pass", "file:" + KEYFILE],
        check=True, capture_output=True,
    )
    os.remove(plain)
    amankan(enc, 0o600)


def dekripsi(enc, plain):
    subprocess.run(
        ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-in", enc,
         "-out", plain, "-pass", "file:" + KEYFILE],
        check=True, capture_output=True,
    )


def offsite_path():
    try:
        with open(OFFSITE_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def backup():
    os.makedirs(OUT, exist_ok=True)
    amankan(OUT, 0o700)
    plain = os.path.join(OUT, "kasir_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".dump")
    path = plain + ".enc"
    jalankan(["pg_dump", "-Fc", "-f", plain, *KONEKSI, "kasir"])
    enkripsi(plain, path)
    lama = sorted(f for f in os.listdir(OUT) if f.endswith(SUFFIX))
    for f in lama[:-KEEP]:
        os.remove(os.path.join(OUT, f))
    tujuan = offsite_path()
    if tujuan and os.path.isdir(tujuan):
        folder = os.path.join(tujuan, "kasir")
        os.makedirs(folder, exist_ok=True)
        amankan(folder, 0o700)
        dest = os.path.join(folder, os.path.basename(path))
        shutil.copy2(path, dest)
        amankan(dest, 0o600)
        lama2 = sorted(f for f in os.listdir(folder) if f.endswith(SUFFIX))
        for f in lama2[:-KEEP]:
            os.remove(os.path.join(folder, f))
        print("Offsite:", dest)
    else:
        print("Offsite: (nonaktif)")
    print(path)


def restore(path, target):
    nama = os.path.basename(path)
    if not re.fullmatch(r"kasir_\d{8}_\d{6}\.dump(?:\.enc)?", nama) or not re.fullmatch(r"[a-z][a-z0-9_]{0,48}", target):
        raise SystemExit("Nama dump atau database tidak valid")
    sementara = None
    try:
        if nama.endswith(".enc"):
            fd, sementara = tempfile.mkstemp(prefix="restore_", suffix=".dump", dir=OUT)
            os.close(fd)
            dekripsi(path, sementara)
            amankan(sementara, 0o600)
        else:
            sementara = path
        jalankan(["createdb", "-T", "template0", *KONEKSI, target])
        jalankan(["pg_restore", "-d", target, *KONEKSI, sementara])
        print("Restored ke database:", target)
    finally:
        if sementara and sementara != path and os.path.exists(sementara):
            os.remove(sementara)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "restore":
        restore(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 1:
        backup()
    else:
        print(__doc__)
        sys.exit(1)
