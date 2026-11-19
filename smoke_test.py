"""Cek cepat API + alur bayar. Jalankan: .venv/bin/python smoke_test.py (server harus aktif)."""
import csv
import io
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = "https://127.0.0.1:8443"
BROWSER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(CookieJar()),
    urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
)


CSRF = {"token": ""}


def minta(path, metode="GET", data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=body, method=metode,
                                 headers={"Content-Type": "application/json",
                                          "X-CSRF-Token": CSRF["token"]})
    try:
        with BROWSER.open(req) as r:
            isi = r.read()
            if "json" not in r.headers.get("Content-Type", ""):
                return r.status, isi.decode("utf-8", "replace")
            return r.status, json.loads(isi or b"{}")
    except urllib.error.HTTPError as e:
        isi = e.read()
        return e.code, json.loads(isi) if isi else {}


# Login dulu: seluruh API butuh sesi kasir.
with open("/home/dana/kasir/ADMIN_PASSWORD.txt") as f:
    admin_pw = f.read().strip()
with BROWSER.open(BASE + "/login") as r:
    html = r.read().decode("utf-8", "replace")
CSRF["token"] = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
login_data = urllib.parse.urlencode({"username": "admin", "password": admin_pw,
                                     "csrf_token": CSRF["token"]}).encode()
with BROWSER.open(BASE + "/login", login_data) as r:
    assert r.status == 200, "login gagal"
with BROWSER.open(BASE + "/api/csrf") as r:
    CSRF["token"] = json.loads(r.read())["token"]
assert minta("/api/shift/buka", "POST", {"awal": 100000})[0] == 201, "buka shift gagal"

status, _ = minta("/")
assert status == 200, "halaman kasir gagal"
status, produk = minta("/api/produk")
assert status == 200 and len(produk) >= 10, "seed 10 produk gagal"

status, baru = minta("/api/produk", "POST", {"nama": "Test Item", "harga": 1000, "stok": 5})
assert status == 201 and baru["nama"] == "Test Item", "tambah produk gagal"
assert minta("/api/produk/" + str(baru["id"]), "PUT",
             {"nama": "Test Item", "harga": 1200, "stok": 5})[0] == 200
status, invoice = minta("/api/transaksi", "POST",
                        {"items": [{"id": baru["id"], "qty": 2}], "diskon": 200,
                         "pajak": 0, "bayar": 2200})
assert status == 201 and invoice["total"] == 2200 and invoice["kembalian"] == 0, "bayar gagal"
assert invoice["kasir_nama"] == "Kasir Utama", "nama kasir tidak tercatat"
assert minta("/api/transaksi", "POST",
             {"items": [{"id": baru["id"], "qty": 1}], "bayar": 0})[0] == 400, "validasi bayar lemah"

_, dashboard = minta("/api/dashboard")
assert dashboard["penjualan"] >= 2200 and dashboard["jumlah"] >= 1, "dashboard salah"
_, riwayat = minta("/api/transaksi")
assert any(t["id"] == invoice["id"] for t in riwayat), "riwayat tidak tersimpan"
assert minta("/api/transaksi/" + str(invoice["id"]))[0] == 200, "detail transaksi gagal"

with BROWSER.open(BASE + "/api/produk/export") as r:
    assert "nama,harga,modal,stok,kategori,gambar" in r.read().decode("utf-8-sig")

assert minta("/api/produk/" + str(baru["id"]), "DELETE")[0] == 200, "hapus produk gagal"
assert minta("/api/shift/tutup", "POST", {"akhir": 100000})[0] == 200, "tutup shift gagal"
print("SEMUAAAN lolos: halaman, CRUD, bayar, validasi, dashboard, riwayat, CSV, shift")
