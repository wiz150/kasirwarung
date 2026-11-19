"""KasirWarung - POS warung: PostgreSQL, upload gambar, login kasir."""
import csv
import io
import os
import re
import subprocess
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from secrets import compare_digest, token_urlsafe
from uuid import uuid4

import psycopg
from flask import (Flask, Response, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)
from psycopg.rows import dict_row
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD = os.path.join(BASE, "static", "img", "produk")
FOTO_TOKO = os.path.join(BASE, "static", "img", "toko")
FOTO_KASIR = os.path.join(BASE, "static", "img", "kasir")
for _folder in (UPLOAD, FOTO_TOKO, FOTO_KASIR):
    os.makedirs(_folder, exist_ok=True)

# libpq env vars (PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD) mengoverride default ini.
def db_password():
    try:
        with open(os.path.join(BASE, "db_password.txt")) as f:
            return f.read().strip()
    except OSError:
        return ""


DSN = os.environ.get(
    "DATABASE_URL",
    f"host=127.0.0.1 port=5432 dbname=kasir user=kasir password={db_password()}",
)
ADMIN_PASSWORD_FILE = os.path.join(BASE, "ADMIN_PASSWORD.txt")
SECRET_FILE = os.path.join(BASE, "secret.key")
BACKUP_DIR = os.path.join(BASE, "backups")
OFFSITE_FILE = os.path.join(BASE, "offsite_path.txt")
PY = os.path.join(BASE, ".venv", "bin", "python")


def kunci_app():
    """SECRET_KEY tetap antar restart; env menang, kalau tidak ada simpan di file 0600."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE) as f:
            return f.read().strip()
    kunci = token_urlsafe(32)
    with open(SECRET_FILE, "w") as f:
        f.write(kunci)
    os.chmod(SECRET_FILE, 0o600)
    return kunci


def simpan_password_admin(password):
    with open(ADMIN_PASSWORD_FILE, "w") as f:
        f.write(password + "\n")
    os.chmod(ADMIN_PASSWORD_FILE, 0o600)


app = Flask(__name__)
app.secret_key = kunci_app()
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = token_urlsafe(24)
    return session["csrf"]


@app.context_processor
def inject_csrf():
    return {"csrf_token": csrf_token}


@app.get("/api/csrf")
def csrf_ambil():
    return jsonify(token=csrf_token())


# Rate limit per IP/kasir disimpan di DB, tetap berlaku setelah restart.


def boleh_coba(kunci, batas=5, jeda=300):
    with db() as c:
        r = c.execute(
            "SELECT jumlah FROM gagal WHERE kunci=%s AND sampai >= LOCALTIMESTAMP", (kunci,)
        ).fetchone()
    return (r["jumlah"] if r else 0) < batas


def catat_gagal(kunci, jeda=300):
    with db() as c:
        c.execute(
            """INSERT INTO gagal (kunci,jumlah,sampai)
               VALUES (%s,1,LOCALTIMESTAMP + (%s || ' seconds')::interval)
               ON CONFLICT (kunci) DO UPDATE SET
                 jumlah = CASE WHEN gagal.sampai < LOCALTIMESTAMP THEN 1 ELSE gagal.jumlah+1 END,
                 sampai = LOCALTIMESTAMP + (%s || ' seconds')::interval""",
            (kunci, str(jeda), str(jeda)),
        )
        c.execute("DELETE FROM gagal WHERE sampai < LOCALTIMESTAMP - INTERVAL '1 day'")


def hapus_gagal(kunci):
    with db() as c:
        c.execute("DELETE FROM gagal WHERE kunci=%s", (kunci,))


@contextmanager
def db():
    """Satu koneksi per request; dict_row bikin hasil bisa diakses sbg dict."""
    conn = psycopg.connect(DSN, row_factory=dict_row)
    try:
        yield conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SKEMA = """
CREATE TABLE IF NOT EXISTS kasir (
    id            SERIAL PRIMARY KEY,
    username      TEXT    NOT NULL UNIQUE,
    nama          TEXT    NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'kasir',
    aktif         BOOLEAN NOT NULL DEFAULT true,
    foto          TEXT    NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sesi (
    token     TEXT PRIMARY KEY,
    kasir_id  INTEGER NOT NULL REFERENCES kasir(id) ON DELETE CASCADE,
    mulai     TIMESTAMP NOT NULL DEFAULT LOCALTIMESTAMP,
    terakhir  TIMESTAMP NOT NULL DEFAULT LOCALTIMESTAMP
);
CREATE TABLE IF NOT EXISTS produk (
    id         SERIAL PRIMARY KEY,
    nama       TEXT    NOT NULL,
    harga      INTEGER NOT NULL CHECK (harga >= 0),
    modal      INTEGER NOT NULL DEFAULT 0 CHECK (modal >= 0),
    stok       INTEGER NOT NULL DEFAULT 0 CHECK (stok >= 0),
    kategori   TEXT    NOT NULL DEFAULT 'Umum',
    gambar     TEXT    NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT LOCALTIMESTAMP
);
CREATE TABLE IF NOT EXISTS transaksi (
    id         SERIAL PRIMARY KEY,
    no         TEXT    NOT NULL UNIQUE,
    tanggal    TEXT    NOT NULL,
    subtotal   INTEGER NOT NULL,
    diskon     INTEGER NOT NULL DEFAULT 0,
    pajak      INTEGER NOT NULL DEFAULT 0,
    total      INTEGER NOT NULL,
    bayar      INTEGER NOT NULL,
    kembalian  INTEGER NOT NULL,
    metode     TEXT    NOT NULL DEFAULT 'Tunai',
    kasir_id   INTEGER NOT NULL REFERENCES kasir(id),
    kasir_nama TEXT    NOT NULL,
    batal      BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS transaksi_item (
    id            SERIAL PRIMARY KEY,
    transaksi_id  INTEGER NOT NULL REFERENCES transaksi(id) ON DELETE CASCADE,
    -- Tanpa FK ke produk: riwayat tetap utuh walau produk dihapus (nama & harga disalin).
    produk_id     INTEGER NOT NULL,
    nama          TEXT    NOT NULL,
    harga         INTEGER NOT NULL,
    modal         INTEGER NOT NULL DEFAULT 0,
    qty           INTEGER NOT NULL CHECK (qty > 0),
    subtotal      INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS kas (
    kasir_id   INTEGER PRIMARY KEY REFERENCES kasir(id),
    saldo      INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT LOCALTIMESTAMP
);
CREATE TABLE IF NOT EXISTS shift (
    id      SERIAL PRIMARY KEY,
    kasir_id INTEGER NOT NULL REFERENCES kasir(id),
    buka    TIMESTAMP NOT NULL DEFAULT LOCALTIMESTAMP,
    tutup   TIMESTAMP,
    awal    INTEGER NOT NULL,
    akhir   INTEGER,
    selisih INTEGER,
    catatan TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_shift_kasir ON shift(kasir_id, buka);
CREATE TABLE IF NOT EXISTS pengaturan (
    kunci TEXT PRIMARY KEY,
    nilai TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nomor (
    kunci TEXT PRIMARY KEY,
    nilai INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS gagal (
    kunci  TEXT PRIMARY KEY,
    jumlah INTEGER NOT NULL,
    sampai TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id       SERIAL PRIMARY KEY,
    waktu    TIMESTAMP NOT NULL DEFAULT LOCALTIMESTAMP,
    kasir_id INTEGER REFERENCES kasir(id),
    aksi     TEXT NOT NULL,
    detail   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_waktu ON audit(waktu);
CREATE INDEX IF NOT EXISTS idx_transaksi_tanggal ON transaksi(tanggal);
"""

SEED = [
    ("Indomie Goreng", 3500, 48, "Makanan"),
    ("Indomie Soto", 3500, 36, "Makanan"),
    ("Nasi Goreng Kampung", 15000, 20, "Makanan"),
    ("Pisang Goreng", 5000, 30, "Makanan"),
    ("Roti Tawar Sari Roti", 17000, 12, "Makanan"),
    ("Teh Botol Sosro 350ml", 5000, 40, "Minuman"),
    ("Aqua 600ml", 4000, 60, "Minuman"),
    ("Kopi Kapal Api Sachet", 2000, 75, "Minuman"),
    ("Sprite 390ml", 6000, 24, "Minuman"),
    ("Chitato Sapi Panggang", 11000, 18, "Snack"),
]


def init_db():
    """Schema + seed awal, aman dijalankan berulang."""
    with db() as c:
        c.execute(SKEMA)
        for sql in (
            "ALTER TABLE kasir ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'kasir'",
            "ALTER TABLE kasir ADD COLUMN IF NOT EXISTS aktif BOOLEAN NOT NULL DEFAULT true",
            "ALTER TABLE transaksi ADD COLUMN IF NOT EXISTS batal BOOLEAN NOT NULL DEFAULT false",
            "ALTER TABLE transaksi ADD COLUMN IF NOT EXISTS alasan_batal TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE kasir ADD COLUMN IF NOT EXISTS foto TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE produk ADD COLUMN IF NOT EXISTS modal INTEGER NOT NULL DEFAULT 0 CHECK (modal >= 0)",
            "ALTER TABLE produk ADD COLUMN IF NOT EXISTS barcode TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE transaksi_item ADD COLUMN IF NOT EXISTS modal INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE transaksi ADD COLUMN IF NOT EXISTS metode TEXT NOT NULL DEFAULT 'Tunai'",
            "ALTER TABLE transaksi ADD COLUMN IF NOT EXISTS shift_id INTEGER REFERENCES shift(id)",
        ):
            c.execute(sql)
        c.execute("UPDATE kasir SET role='admin' WHERE username='admin'")
        if not c.execute("SELECT 1 FROM kasir LIMIT 1").fetchone():
            c.execute(
                "INSERT INTO kasir (username,nama,password_hash,role) VALUES (%s,%s,%s,%s)",
                ("admin", "Kasir Utama", generate_password_hash("admin123"), "admin"),
            )
        if not c.execute("SELECT 1 FROM produk LIMIT 1").fetchone():
            c.executemany(
                "INSERT INTO produk (nama,harga,stok,kategori) VALUES (%s,%s,%s,%s)", SEED
            )
        # Password bawaan tidak boleh dipakai di aplikasi nyata.
        admin = c.execute(
            "SELECT id,password_hash FROM kasir WHERE username='admin'"
        ).fetchone()
        if admin and check_password_hash(admin["password_hash"], "admin123"):
            password = os.environ.get("ADMIN_PASSWORD") or token_urlsafe(9)
            c.execute("UPDATE kasir SET password_hash=%s WHERE id=%s",
                      (generate_password_hash(password), admin["id"]))
            simpan_password_admin(password)
            print(f"Password admin pertama dibuat di {ADMIN_PASSWORD_FILE}")


def bilangan(nilai, nama, min=0):
    """Validasi input angka di trust boundary API."""
    try:
        n = int(nilai)
    except (TypeError, ValueError):
        raise ValueError(f"{nama} harus angka")
    if n < min:
        raise ValueError(f"{nama} tidak boleh kurang dari {min}")
    return n


def rupiah(n):
    return "Rp " + f"{int(n or 0):,}".replace(",", ".")


def tanggal_arg(nilai, nama):
    s = str(nilai or "").strip()
    if not s:
        return ""
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"{nama} tidak valid")
    return s


def catat(aksi, detail=""):
    """Audit ke DB; kasir_id kosong untuk peristiwa tanpa sesi (mis. login gagal)."""
    with db() as c:
        c.execute(
            "INSERT INTO audit (kasir_id,aksi,detail) VALUES (%s,%s,%s)",
            (session.get("kasir_id"), aksi, str(detail)[:300]),
        )


def toko_db():
    with db() as c:
        rows = c.execute("SELECT kunci,nilai FROM pengaturan WHERE kunci LIKE 'toko_%'").fetchall()
    nilai = {r["kunci"]: r["nilai"] for r in rows}
    return {
        "nama": nilai.get("toko_nama") or "KASIR WARUNG",
        "alamat": nilai.get("toko_alamat") or "Jl. Raya Merdeka No. 1 · Toko Anda",
        "telepon": nilai.get("toko_telepon") or "",
        "footer": nilai.get("toko_footer") or "Terima kasih sudah berbelanja",
        "foto": nilai.get("toko_foto") or "",
    }


@app.context_processor
def inject_toko():
    return {"toko": toko_db()}


def data_produk():
    """Form multipart (upload) atau JSON, diperlakukan sama."""
    if request.form or request.files:
        return request.form
    return request.get_json(silent=True) or {}


def ambil_gambar(d):
    """Simpan file upload, kembalikan path statisnya; tanpa file pakai path lama."""
    f = request.files.get("file_gambar")
    if f and f.filename:
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in {"jpg", "jpeg", "png", "gif", "webp"}:
            raise ValueError("Format gambar harus jpg/png/gif/webp")
        nama = uuid4().hex + "." + ext
        f.save(os.path.join(UPLOAD, nama))
        return "/static/img/produk/" + nama
    return str(d.get("gambar") or "").strip()


def simpan_foto(folder, file):
    """Simpan foto upload ke folder statis, kembalikan path-nya."""
    if not file or not file.filename:
        return ""
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in {"jpg", "jpeg", "png", "gif", "webp"}:
        raise ValueError("Format foto harus jpg/png/gif/webp")
    nama = uuid4().hex + "." + ext
    file.save(os.path.join(BASE, "static", "img", folder, nama))
    return f"/static/img/{folder}/{nama}"


# ---------- Auth ----------
ADMIN_ENDPOINTS = {
    "halaman_produk", "halaman_dashboard", "halaman_akun",
    "produk_tambah", "produk_ubah", "produk_hapus", "produk_import", "produk_export",
    "dashboard_data", "kasir_list", "kasir_tambah", "kasir_ubah", "kasir_aktif",
    "kasir_reset", "kasir_hapus", "kode_cetak_status", "kode_cetak_set",
    "audit_list", "transaksi_batal", "stok_opname", "shift_admin_tutup",
    "backup_list", "backup_jalan", "backup_offsite", "restore_jalan",
    "toko_get", "toko_set", "transaksi_export", "toko_foto_set", "kas_set",
}


@app.before_request
def wajib_login():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.endpoint != "static":
        dikirim = (request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
                   or (request.get_json(silent=True) or {}).get("csrf_token"))
        if not session.get("csrf") or not dikirim or not compare_digest(str(session["csrf"]), str(dikirim)):
            if request.path.startswith("/api/"):
                return jsonify(error="CSRF token tidak valid"), 400
            return "CSRF token tidak valid", 400
    if request.endpoint in ("login", "static"):
        return None
    if not session.get("kasir_id"):
        if request.path.startswith("/api/"):
            return jsonify(error="Belum login"), 401
        return redirect(url_for("login", next=request.path))
    with db() as c:
        u = c.execute("SELECT role,aktif,foto FROM kasir WHERE id=%s", (session["kasir_id"],)).fetchone()
        if not u or not u["aktif"]:
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify(error="Akun tidak aktif"), 403
            return redirect(url_for("login"))
        session["role"] = u["role"]
        session["kasir_foto"] = u["foto"]
        if "token" not in session:
            token = token_urlsafe(16)
            session["token"] = token
            c.execute("INSERT INTO sesi (token,kasir_id) VALUES (%s,%s)", (token, session["kasir_id"]))
        c.execute("UPDATE sesi SET terakhir=LOCALTIMESTAMP WHERE token=%s", (session["token"],))
    if request.endpoint in ADMIN_ENDPOINTS and session.get("role") != "admin":
        if request.path.startswith("/api/"):
            return jsonify(error="Hanya admin"), 403
        return redirect(url_for("halaman_kasir"))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    kunci = f"login:{request.remote_addr}"
    if request.method == "POST":
        if not boleh_coba(kunci):
            return render_template(
                "login.html", error="Terlalu banyak percobaan. Coba lagi beberapa menit."
            ), 429
        username = str(request.form.get("username") or "").strip()
        with db() as c:
            u = c.execute("SELECT * FROM kasir WHERE username=%s", (username,)).fetchone()
        if u and u["aktif"] and check_password_hash(u["password_hash"], str(request.form.get("password") or "")):
            hapus_gagal(kunci)
            token = token_urlsafe(16)
            session.clear()
            session["csrf"] = token_urlsafe(24)
            session["kasir_id"] = u["id"]
            session["kasir_nama"] = u["nama"]
            session["kasir_foto"] = u["foto"]
            session["role"] = u["role"]
            session["token"] = token
            with db() as c:
                c.execute("INSERT INTO sesi (token,kasir_id) VALUES (%s,%s)", (token, u["id"]))
            catat("login", username)
            lanjut = request.args.get("next") or "/"
            if not lanjut.startswith("/") or lanjut.startswith("//"):
                lanjut = "/"
            return redirect(lanjut)
        catat_gagal(kunci)
        catat("login_gagal", username)
        error = "Username atau password salah"
    return render_template("login.html", error=error), (401 if error else 200)


@app.get("/logout")
def logout():
    kid = session.get("kasir_id")
    if kid:
        with db() as c:
            aktif = c.execute(
                "SELECT 1 FROM shift WHERE kasir_id=%s AND tutup IS NULL", (kid,)
            ).fetchone()
        if aktif:
            return redirect(url_for("logout_shift"))
    return keluar()


def keluar():
    catat("logout", session.get("kasir_nama", ""))
    if session.get("token"):
        with db() as c:
            c.execute("DELETE FROM sesi WHERE token=%s", (session["token"],))
    session.clear()
    return redirect(url_for("login"))


@app.route("/logout-shift", methods=["GET", "POST"])
def logout_shift():
    kid = session.get("kasir_id")
    if not kid:
        return redirect(url_for("login"))
    with db() as c:
        s = c.execute(
            "SELECT id,awal,buka FROM shift WHERE kasir_id=%s AND tutup IS NULL", (kid,)
        ).fetchone()
        if not s:
            return redirect(url_for("logout"))
        if request.method == "POST":
            try:
                akhir = bilangan(request.form.get("akhir"), "Uang akhir")
            except ValueError as e:
                return render_template("logout_shift.html", error=str(e)), 400
            hasil = tutup_shift_di_db(c, kid, akhir, str(request.form.get("catatan") or "").strip()[:200])
            catat("shift_tutup", f"selisih {hasil['selisih']} (logout)")
            return keluar()
        tunai = c.execute(
            """SELECT COALESCE(SUM(total),0) AS total FROM transaksi
               WHERE shift_id=%s AND metode='Tunai' AND NOT batal""", (s["id"],)
        ).fetchone()["total"]
    return render_template("logout_shift.html", error=None, tunai=tunai, harapan=s["awal"] + tunai)


@app.get("/api/kasir")
def kasir_list():
    """Daftar akun kasir + status sedang digunakan (aktif 15 menit terakhir)."""
    with db() as c:
        rows = c.execute(
            """SELECT k.id, k.username, k.nama, k.role, k.aktif,
                      MAX(COALESCE(ks.saldo,0)) AS saldo,
                      COALESCE(MAX(s.terakhir) >= LOCALTIMESTAMP - INTERVAL '15 minutes', false) AS online,
                      TO_CHAR(MAX(s.terakhir), 'YYYY-MM-DD HH24:MI') AS terakhir
               FROM kasir k
               LEFT JOIN sesi s ON s.kasir_id=k.id
               LEFT JOIN kas ks ON ks.kasir_id=k.id
               GROUP BY k.id ORDER BY k.id"""
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/kasir")
def kasir_tambah():
    """Hanya admin yang bisa membuat akun kasir."""
    d = request.get_json(silent=True) or {}
    username = str(d.get("username") or "").strip()
    nama = str(d.get("nama") or "").strip()
    password = str(d.get("password") or "")
    if not username or not nama or not password:
        return jsonify(error="Username, nama, dan password wajib diisi"), 400
    if len(password) < 6:
        return jsonify(error="Password minimal 6 karakter"), 400
    with db() as c:
        if c.execute("SELECT 1 FROM kasir WHERE username=%s", (username,)).fetchone():
            return jsonify(error="Username sudah dipakai"), 409
        row = c.execute(
            """INSERT INTO kasir (username,nama,password_hash,role)
               VALUES (%s,%s,%s,'kasir') RETURNING id,username,nama,role""",
            (username, nama, generate_password_hash(password)),
        ).fetchone()
    return jsonify(dict(row)), 201


def admin_terakhir(c, kid, role_baru):
    """Tolak penurunan/nonaktifasi admin jika itu satu-satunya admin aktif."""
    if role_baru == "admin":
        return False
    u = c.execute("SELECT role,aktif FROM kasir WHERE id=%s", (kid,)).fetchone()
    if not u or u["role"] != "admin" or not u["aktif"]:
        return False
    return c.execute("SELECT COUNT(*) AS n FROM kasir WHERE role='admin' AND aktif").fetchone()["n"] <= 1


@app.put("/api/kasir/<int:kid>")
def kasir_ubah(kid):
    d = request.get_json(silent=True) or {}
    nama = str(d.get("nama") or "").strip()
    role = str(d.get("role") or "kasir")
    if not nama or role not in ("admin", "kasir"):
        return jsonify(error="Nama wajib diisi dan role harus admin/kasir"), 400
    with db() as c:
        if admin_terakhir(c, kid, role):
            return jsonify(error="Admin terakhir tidak bisa diturunkan"), 400
        row = c.execute(
            "UPDATE kasir SET nama=%s,role=%s WHERE id=%s RETURNING id,username,nama,role,aktif",
            (nama, role, kid),
        ).fetchone()
    if not row:
        return jsonify(error="Akun tidak ditemukan"), 404
    catat("kasir_diubah", row["username"])
    return jsonify(dict(row))


@app.post("/api/kasir/<int:kid>/aktif")
def kasir_aktif(kid):
    aktif = bool((request.get_json(silent=True) or {}).get("aktif"))
    if kid == session["kasir_id"] and not aktif:
        return jsonify(error="Tidak bisa menonaktifkan akun sendiri"), 400
    with db() as c:
        if admin_terakhir(c, kid, "kasir") and not aktif:
            return jsonify(error="Admin terakhir tidak bisa dinonaktifkan"), 400
        row = c.execute(
            "UPDATE kasir SET aktif=%s WHERE id=%s RETURNING id,username,aktif", (aktif, kid)
        ).fetchone()
        if not row:
            return jsonify(error="Akun tidak ditemukan"), 404
        if not aktif:
            c.execute("DELETE FROM sesi WHERE kasir_id=%s", (kid,))
    catat("kasir_aktif", f"{row['username']}={aktif}")
    return jsonify(dict(row))


@app.post("/api/kasir/<int:kid>/reset")
def kasir_reset(kid):
    password = str((request.get_json(silent=True) or {}).get("password") or "")
    if len(password) < 6:
        return jsonify(error="Password minimal 6 karakter"), 400
    with db() as c:
        row = c.execute(
            "UPDATE kasir SET password_hash=%s WHERE id=%s RETURNING username",
            (generate_password_hash(password), kid),
        ).fetchone()
    if not row:
        return jsonify(error="Akun tidak ditemukan"), 404
    if row["username"] == "admin":
        simpan_password_admin(password)
    catat("kasir_reset", row["username"])
    return jsonify(ok=True)


@app.delete("/api/kasir/<int:kid>")
def kasir_hapus(kid):
    if kid == session["kasir_id"]:
        return jsonify(error="Tidak bisa menghapus akun sendiri"), 400
    with db() as c:
        u = c.execute("SELECT username FROM kasir WHERE id=%s", (kid,)).fetchone()
        if not u:
            return jsonify(error="Akun tidak ditemukan"), 404
        if admin_terakhir(c, kid, "kasir"):
            return jsonify(error="Admin terakhir tidak bisa dihapus"), 400
        if c.execute("SELECT 1 FROM transaksi WHERE kasir_id=%s LIMIT 1", (kid,)).fetchone():
            return jsonify(error="Akun punya transaksi — nonaktifkan saja"), 409
        c.execute("UPDATE audit SET kasir_id=NULL WHERE kasir_id=%s", (kid,))
        c.execute("DELETE FROM sesi WHERE kasir_id=%s", (kid,))
        c.execute("DELETE FROM kasir WHERE id=%s", (kid,))
    catat("kasir_hapus", u["username"])
    return jsonify(ok=True)


@app.post("/api/kas/<int:kid>")
def kas_set(kid):
    """Admin menyet saldo kas seorang kasir (nilai absolut)."""
    d = request.get_json(silent=True) or {}
    try:
        saldo = bilangan(d.get("saldo"), "Saldo")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    alasan = str(d.get("alasan") or "penyesuaian").strip()[:100]
    with db() as c:
        if not c.execute("SELECT 1 FROM kasir WHERE id=%s", (kid,)).fetchone():
            return jsonify(error="Akun tidak ditemukan"), 404
        c.execute(
            """INSERT INTO kas (kasir_id,saldo) VALUES (%s,%s)
               ON CONFLICT (kasir_id) DO UPDATE SET saldo=EXCLUDED.saldo, updated_at=LOCALTIMESTAMP""",
            (kid, saldo),
        )
    catat("kas_diubah", f"kasir#{kid} ({alasan}) -> {saldo}")
    return jsonify(saldo=saldo)


@app.post("/api/shift/buka")
def shift_buka():
    try:
        awal = bilangan((request.get_json(silent=True) or {}).get("awal"), "Uang awal")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    with db() as c:
        if c.execute("SELECT 1 FROM shift WHERE kasir_id=%s AND tutup IS NULL", (session["kasir_id"],)).fetchone():
            return jsonify(error="Masih ada shift aktif"), 409
        row = c.execute(
            "INSERT INTO shift (kasir_id,awal) VALUES (%s,%s) RETURNING id,awal,buka",
            (session["kasir_id"], awal),
        ).fetchone()
    catat("shift_buka", str(awal))
    return jsonify(dict(row)), 201


def tutup_shift_di_db(c, kasir_id, akhir, catatan, shift_id=None):
    if shift_id:
        s = c.execute(
            "SELECT id,awal,buka FROM shift WHERE id=%s AND tutup IS NULL", (shift_id,)
        ).fetchone()
    else:
        s = c.execute(
            "SELECT id,awal,buka FROM shift WHERE kasir_id=%s AND tutup IS NULL", (kasir_id,)
        ).fetchone()
    if not s:
        return None
    tunai = c.execute(
        """SELECT COALESCE(SUM(total),0) AS total FROM transaksi
           WHERE shift_id=%s AND metode='Tunai' AND NOT batal""",
        (s["id"],),
    ).fetchone()["total"]
    harapan = s["awal"] + tunai
    selisih = akhir - harapan
    c.execute(
        "UPDATE shift SET tutup=LOCALTIMESTAMP, akhir=%s, selisih=%s, catatan=%s WHERE id=%s",
        (akhir, selisih, catatan, s["id"]),
    )
    return {"tunai": tunai, "harapan": harapan, "selisih": selisih}


@app.post("/api/shift/tutup")
def shift_tutup():
    d = request.get_json(silent=True) or {}
    try:
        akhir = bilangan(d.get("akhir"), "Uang akhir")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    catatan = str(d.get("catatan") or "").strip()[:200]
    with db() as c:
        hasil = tutup_shift_di_db(c, session["kasir_id"], akhir, catatan)
    if not hasil:
        return jsonify(error="Tidak ada shift aktif"), 404
    catat("shift_tutup", f"selisih {hasil['selisih']}")
    return jsonify(**hasil)


@app.get("/api/shift")
def shift_list():
    with db() as c:
        where = "" if session.get("role") == "admin" else "WHERE s.kasir_id=%s"
        args = () if session.get("role") == "admin" else (session["kasir_id"],)
        rows = c.execute(
            f"""SELECT s.id, s.kasir_id, k.nama AS kasir,
                       TO_CHAR(s.buka,'YYYY-MM-DD HH24:MI') AS buka,
                       TO_CHAR(s.tutup,'YYYY-MM-DD HH24:MI') AS tutup,
                       s.awal, s.akhir, s.selisih, s.catatan,
                       (SELECT COALESCE(SUM(t.total),0) FROM transaksi t
                        WHERE t.shift_id=s.id AND t.metode='Tunai' AND NOT t.batal) AS tunai
                FROM shift s JOIN kasir k ON k.id=s.kasir_id
                {where} ORDER BY s.id DESC LIMIT 100""",
            args,
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/shift/<int:sid>/admin-tutup")
def shift_admin_tutup(sid):
    d = request.get_json(silent=True) or {}
    try:
        akhir = bilangan(d.get("akhir"), "Uang akhir")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    catatan = str(d.get("catatan") or "").strip()[:200]
    with db() as c:
        hasil = tutup_shift_di_db(c, None, akhir, catatan, shift_id=sid)
    if not hasil:
        return jsonify(error="Shift tidak ditemukan atau sudah ditutup"), 404
    catat("shift_tutup", f"admin menutup shift#{sid}, selisih {hasil['selisih']}")
    return jsonify(**hasil)


@app.get("/api/audit")
def audit_list():
    with db() as c:
        rows = c.execute(
            """SELECT TO_CHAR(a.waktu,'YYYY-MM-DD HH24:MI') AS waktu,
                      COALESCE(k.nama,'-') AS kasir, a.aksi, a.detail
               FROM audit a LEFT JOIN kasir k ON k.id=a.kasir_id
               ORDER BY a.id DESC LIMIT 200"""
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.get("/api/backup")
def backup_list():
    files = []
    if os.path.isdir(BACKUP_DIR):
        for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
            if re.fullmatch(r"kasir_\d{8}_\d{6}\.dump(?:\.enc)?", f):
                files.append({"nama": f, "ukuran": os.path.getsize(os.path.join(BACKUP_DIR, f))})
    try:
        with open(OFFSITE_FILE) as f:
            offsite = f.read().strip()
    except OSError:
        offsite = ""
    return jsonify(files=files, offsite=offsite)


@app.post("/api/backup")
def backup_jalan():
    r = subprocess.run(
        [PY, os.path.join(BASE, "backup.py")], capture_output=True, text=True, timeout=180
    )
    if r.returncode:
        return jsonify(error=r.stderr.strip()[-300:]), 500
    catat("backup", "manual")
    return jsonify(ok=True, out=r.stdout.strip())


@app.post("/api/backup/offsite")
def backup_offsite():
    path = str((request.get_json(silent=True) or {}).get("path") or "").strip()
    if path and (not os.path.isabs(path) or not os.path.isdir(path)):
        return jsonify(error="Path harus folder absolut yang sudah ada"), 400
    with open(OFFSITE_FILE, "w") as f:
        f.write(path)
    os.chmod(OFFSITE_FILE, 0o600)
    catat("offsite_diubah", path or "(dinonaktifkan)")
    return jsonify(ok=True)


@app.post("/api/restore")
def restore_jalan():
    d = request.get_json(silent=True) or {}
    nama = str(d.get("file") or "")
    target = str(d.get("db") or "").strip()
    if not re.fullmatch(r"kasir_\d{8}_\d{6}\.dump(?:\.enc)?", nama) or not re.fullmatch(r"[a-z][a-z0-9_]{0,48}", target):
        return jsonify(error="Nama dump atau database tidak valid"), 400
    source = os.path.join(BACKUP_DIR, nama)
    if not os.path.exists(source):
        return jsonify(error="Dump tidak ditemukan"), 404
    r = subprocess.run(
        [PY, os.path.join(BASE, "backup.py"), "restore", source, target],
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode:
        return jsonify(error=r.stderr.strip()[-300:]), 500
    catat("restore", f"{nama} -> {target}")
    return jsonify(ok=True)


@app.get("/api/kode-cetak")
def kode_cetak_status():
    with db() as c:
        ada = c.execute("SELECT 1 FROM pengaturan WHERE kunci='kode_cetak'").fetchone()
    return jsonify(sudah_ada=bool(ada))


@app.post("/api/kode-cetak")
def kode_cetak_set():
    """Admin menset kode yang dipakai kasir untuk mencetak struk."""
    kode = str((request.get_json(silent=True) or {}).get("kode") or "")
    if len(kode) < 4:
        return jsonify(error="Kode minimal 4 karakter"), 400
    with db() as c:
        c.execute(
            """INSERT INTO pengaturan (kunci,nilai) VALUES ('kode_cetak',%s)
               ON CONFLICT (kunci) DO UPDATE SET nilai=EXCLUDED.nilai""",
            (generate_password_hash(kode),),
        )
    catat("kode_cetak", "diubah")
    return jsonify(ok=True)


@app.get("/api/toko")
def toko_get():
    return jsonify(toko_db())


@app.post("/api/toko")
def toko_set():
    d = request.get_json(silent=True) or {}
    vals = {
        "toko_nama": str(d.get("nama") or "").strip(),
        "toko_alamat": str(d.get("alamat") or "").strip(),
        "toko_telepon": str(d.get("telepon") or "").strip(),
        "toko_footer": str(d.get("footer") or "").strip() or "Terima kasih sudah berbelanja",
    }
    if not vals["toko_nama"]:
        vals["toko_nama"] = "KASIR WARUNG"  # fallback kalau field dikosongkan
    with db() as c:
        for kunci, nilai in vals.items():
            c.execute(
                """INSERT INTO pengaturan (kunci,nilai) VALUES (%s,%s)
                   ON CONFLICT (kunci) DO UPDATE SET nilai=EXCLUDED.nilai""",
                (kunci, nilai),
            )
    catat("toko_diubah", vals["toko_nama"])
    return jsonify(ok=True)


@app.post("/api/toko/foto")
def toko_foto_set():
    try:
        path = simpan_foto("toko", request.files.get("foto"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if not path:
        return jsonify(error="Pilih foto toko"), 400
    with db() as c:
        c.execute(
            """INSERT INTO pengaturan (kunci,nilai) VALUES ('toko_foto',%s)
               ON CONFLICT (kunci) DO UPDATE SET nilai=EXCLUDED.nilai""",
            (path,),
        )
    catat("toko_foto", path)
    return jsonify(foto=path)


@app.get("/api/profil")
def profil_get():
    with db() as c:
        row = c.execute(
            "SELECT id,username,nama,role,foto FROM kasir WHERE id=%s", (session["kasir_id"],)
        ).fetchone()
    return jsonify(dict(row))


@app.post("/api/profil/foto")
def profil_foto_set():
    try:
        path = simpan_foto("kasir", request.files.get("foto"))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if not path:
        return jsonify(error="Pilih foto profil"), 400
    with db() as c:
        c.execute("UPDATE kasir SET foto=%s WHERE id=%s", (path, session["kasir_id"]))
    session["kasir_foto"] = path
    catat("foto_profil", session["kasir_nama"])
    return jsonify(foto=path)


@app.post("/api/cetak")
def cetak_verifikasi():
    """Kasir harus memasukkan kode dari admin sebelum mencetak."""
    d = request.get_json(silent=True) or {}
    kode = str(d.get("kode") or "")
    no = str(d.get("no") or "")
    kunci = f"cetak:{session['kasir_id']}"
    if not boleh_coba(kunci):
        return jsonify(error="Terlalu banyak percobaan kode. Coba lagi beberapa menit."), 429
    with db() as c:
        row = c.execute("SELECT nilai FROM pengaturan WHERE kunci='kode_cetak'").fetchone()
    if not row or not check_password_hash(row["nilai"], kode):
        catat_gagal(kunci)
        catat("cetak_gagal", no)
        return jsonify(error="Kode cetak salah atau belum diset admin"), 403
    hapus_gagal(kunci)
    catat("cetak", no)
    return jsonify(ok=True)


# ---------- Halaman ----------
@app.get("/")
def halaman_kasir():
    return render_template("index.html", title="Kasir")


@app.get("/produk")
def halaman_produk():
    return render_template("produk.html", title="Produk")


@app.get("/riwayat")
def halaman_riwayat():
    return render_template("riwayat.html", title="Riwayat")


@app.get("/dashboard")
def halaman_dashboard():
    return render_template("dashboard.html", title="Dashboard")


@app.get("/akun")
def halaman_akun():
    return render_template("akun.html", title="Kasir & Sesi")


@app.get("/pengaturan")
def halaman_pengaturan():
    return render_template("pengaturan.html", title="Pengaturan")


# ---------- API produk ----------
@app.get("/api/produk")
def produk_list():
    q = f"%{request.args.get('q', '').strip()}%"
    with db() as c:
        rows = c.execute(
            "SELECT * FROM produk WHERE nama LIKE %s OR kategori LIKE %s ORDER BY id DESC",
            (q, q),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/produk")
def produk_tambah():
    d = data_produk()
    try:
        nama = str(d.get("nama", "")).strip()
        if not nama:
            raise ValueError("Nama wajib diisi")
        harga = bilangan(d.get("harga"), "Harga")
        modal = bilangan(d.get("modal") or 0, "Modal")
        stok = bilangan(d.get("stok"), "Stok")
        gambar = ambil_gambar(d)
        barcode = str(d.get("barcode") or "").strip()[:64]
    except ValueError as e:
        return jsonify(error=str(e)), 400
    with db() as c:
        if barcode and c.execute("SELECT 1 FROM produk WHERE barcode=%s", (barcode,)).fetchone():
            return jsonify(error="Barcode sudah dipakai produk lain"), 400
        row = c.execute(
            "INSERT INTO produk (nama,harga,modal,stok,kategori,gambar,barcode) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (nama, harga, modal, stok, str(d.get("kategori") or "Umum").strip(), gambar, barcode),
        ).fetchone()
    return jsonify(dict(row)), 201


@app.put("/api/produk/<int:pid>")
def produk_ubah(pid):
    d = data_produk()
    try:
        nama = str(d.get("nama", "")).strip()
        if not nama:
            raise ValueError("Nama wajib diisi")
        harga = bilangan(d.get("harga"), "Harga")
        modal = bilangan(d.get("modal") or 0, "Modal")
        stok = bilangan(d.get("stok"), "Stok")
        gambar = ambil_gambar(d)
        barcode = str(d.get("barcode") or "").strip()[:64]
    except ValueError as e:
        return jsonify(error=str(e)), 400
    with db() as c:
        if not c.execute("SELECT 1 FROM produk WHERE id=%s", (pid,)).fetchone():
            return jsonify(error="Produk tidak ditemukan"), 404
        if barcode and c.execute("SELECT 1 FROM produk WHERE barcode=%s AND id<>%s", (barcode, pid)).fetchone():
            return jsonify(error="Barcode sudah dipakai produk lain"), 400
        row = c.execute(
            "UPDATE produk SET nama=%s,harga=%s,modal=%s,stok=%s,kategori=%s,gambar=%s,barcode=%s WHERE id=%s RETURNING *",
            (nama, harga, modal, stok, str(d.get("kategori") or "Umum").strip(), gambar, barcode, pid),
        ).fetchone()
    return jsonify(dict(row))


@app.post("/api/produk/<int:pid>/stok")
def stok_opname(pid):
    d = request.get_json(silent=True) or {}
    try:
        stok = bilangan(d.get("stok"), "Stok")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    alasan = str(d.get("alasan") or "opname").strip()[:100]
    with db() as c:
        row = c.execute(
            "UPDATE produk SET stok=%s WHERE id=%s RETURNING id,nama,stok", (stok, pid)
        ).fetchone()
    if not row:
        return jsonify(error="Produk tidak ditemukan"), 404
    catat("stok_opname", f"{row['nama']} ({alasan}) -> {stok}")
    return jsonify(dict(row))


@app.delete("/api/produk/<int:pid>")
def produk_hapus(pid):
    with db() as c:
        if not c.execute("SELECT 1 FROM produk WHERE id=%s", (pid,)).fetchone():
            return jsonify(error="Produk tidak ditemukan"), 404
        # Riwayat transaksi tetap aman: transaksi_item menyimpan salinan nama & harga.
        c.execute("DELETE FROM produk WHERE id=%s", (pid,))
    return jsonify(ok=True)


@app.post("/api/produk/import")
def produk_import():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".csv"):
        return jsonify(error="Pilih file .csv"), 400
    try:
        teks = f.read().decode("utf-8-sig")
        baris = list(csv.DictReader(io.StringIO(teks)))
        if not baris:
            raise ValueError("CSV kosong")
        data = []
        for r in baris:
            data.append(
                (
                    str(r.get("nama") or "").strip(),
                    bilangan(r.get("harga"), "harga"),
                    bilangan(r.get("modal") or 0, "modal"),
                    bilangan(r.get("stok"), "stok"),
                    str(r.get("kategori") or "Umum").strip(),
                    str(r.get("gambar") or "").strip(),
                    str(r.get("barcode") or "").strip()[:64],
                )
            )
        if any(not d[0] for d in data):
            raise ValueError("Ada baris tanpa nama")
    except (ValueError, UnicodeDecodeError) as e:
        return jsonify(error=f"CSV tidak valid: {e}"), 400
    with db() as c:
        c.executemany(
            "INSERT INTO produk (nama,harga,modal,stok,kategori,gambar,barcode) VALUES (%s,%s,%s,%s,%s,%s,%s)", data
        )
    return jsonify(imported=len(data)), 201


@app.get("/api/produk/export")
def produk_export():
    with db() as c:
        rows = c.execute("SELECT nama,harga,modal,stok,kategori,gambar,barcode FROM produk ORDER BY id").fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["nama", "harga", "modal", "stok", "kategori", "gambar", "barcode"])
    w.writerows([tuple(r.values()) for r in rows])
    return Response(
        "\ufeff" + out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=produk.csv"},
    )


# ---------- API transaksi ----------
@app.get("/api/transaksi")
def transaksi_list():
    dari = request.args.get("dari", "")
    sampai = request.args.get("sampai", "")
    bat = request.args.get("limit")
    ofs = request.args.get("offset")
    try:
        dari = tanggal_arg(dari, "Dari")
        sampai = tanggal_arg(sampai, "Sampai")
        limit = bilangan(bat, "Limit", min=1) if bat else 0
        offset = bilangan(ofs, "Offset") if ofs else 0
    except ValueError as e:
        return jsonify(error=str(e)), 400
    sql = "SELECT * FROM transaksi WHERE 1=1"
    args = []
    if session.get("role") != "admin":
        sql += " AND kasir_id=%s"
        args.append(session["kasir_id"])
    if dari:
        sql += " AND tanggal::date >= %s"
        args.append(dari)
    if sampai:
        sql += " AND tanggal::date <= %s"
        args.append(sampai)
    where_sql = sql[len("SELECT * FROM transaksi"):]
    with db() as c:
        if limit:
            agregat = c.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(total) FILTER (WHERE NOT batal),0) AS s FROM transaksi" + where_sql,
                args,
            ).fetchone()
        sql += " ORDER BY id DESC"
        if limit:
            sql += " LIMIT %s OFFSET %s"
            args += [limit, offset]
        tx = [dict(r) for r in c.execute(sql, args).fetchall()]
        for t in tx:
            t["items"] = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM transaksi_item WHERE transaksi_id=%s", (t["id"],)
                ).fetchall()
            ]
    resp = jsonify(tx)
    if limit:
        resp.headers["X-Total"] = str(agregat["n"])
        resp.headers["X-Subtotal"] = str(agregat["s"])
    return resp


@app.get("/api/transaksi/export")
def transaksi_export():
    """Admin: ekspor riwayat (filter tanggal yang sama seperti halaman Riwayat)."""
    dari = request.args.get("dari", "")
    sampai = request.args.get("sampai", "")
    try:
        dari = tanggal_arg(dari, "Dari")
        sampai = tanggal_arg(sampai, "Sampai")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    sql = "SELECT * FROM transaksi WHERE 1=1"
    args = []
    if dari:
        sql += " AND tanggal::date >= %s"
        args.append(dari)
    if sampai:
        sql += " AND tanggal::date <= %s"
        args.append(sampai)
    sql += " ORDER BY id DESC"
    with db() as c:
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["No", "Tanggal", "Kasir", "Metode", "Item", "Subtotal", "Diskon", "Pajak",
                    "Total", "Bayar", "Kembalian", "Status", "Alasan batal"])
        for t in c.execute(sql, args).fetchall():
            items = "; ".join(
                "{} x{} @ {}".format(i["nama"], i["qty"], i["harga"])
                for i in c.execute(
                    "SELECT nama,qty,harga FROM transaksi_item WHERE transaksi_id=%s", (t["id"],)
                ).fetchall()
            )
            w.writerow([t["no"], t["tanggal"], t["kasir_nama"], t["metode"], items, t["subtotal"],
                        t["diskon"], t["pajak"], t["total"], t["bayar"], t["kembalian"],
                        "BATAL" if t["batal"] else "", t["alasan_batal"] or ""])
    return Response(
        "\ufeff" + out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=riwayat.csv"},
    )


@app.get("/api/transaksi/<int:tid>")
def transaksi_detail(tid):
    with db() as c:
        row = c.execute("SELECT * FROM transaksi WHERE id=%s", (tid,)).fetchone()
        if not row:
            return jsonify(error="Transaksi tidak ditemukan"), 404
        if session.get("role") != "admin" and row["kasir_id"] != session["kasir_id"]:
            return jsonify(error="Transaksi tidak ditemukan"), 404
        tx = dict(row)
        tx["items"] = [
            dict(r)
            for r in c.execute("SELECT * FROM transaksi_item WHERE transaksi_id=%s", (tid,)).fetchall()
        ]
    return jsonify(tx)


@app.post("/api/transaksi/<int:tid>/batal")
def transaksi_batal(tid):
    """Admin membatalkan transaksi dan mengembalikan stok barangnya."""
    d = request.get_json(silent=True) or {}
    alasan = str(d.get("alasan") or "").strip()[:200]
    if len(alasan) < 3:
        return jsonify(error="Alasan pembatalan wajib diisi (minimal 3 karakter)"), 400
    with db() as c:
        t = c.execute("SELECT no,batal,metode,total,kasir_id FROM transaksi WHERE id=%s", (tid,)).fetchone()
        if not t:
            return jsonify(error="Transaksi tidak ditemukan"), 404
        if t["batal"]:
            return jsonify(error="Transaksi sudah dibatalkan"), 400
        c.execute("UPDATE transaksi SET batal=true, alasan_batal=%s WHERE id=%s", (alasan, tid))
        if t["metode"] == "Tunai":
            c.execute("UPDATE kas SET saldo=saldo-%s, updated_at=LOCALTIMESTAMP WHERE kasir_id=%s",
                      (t["total"], t["kasir_id"]))
        for i in c.execute(
            "SELECT produk_id,qty FROM transaksi_item WHERE transaksi_id=%s", (tid,)
        ).fetchall():
            c.execute("UPDATE produk SET stok=stok+%s WHERE id=%s", (i["qty"], i["produk_id"]))
    catat("transaksi_batal", f"{t['no']} — {alasan}")
    return jsonify(ok=True)


@app.post("/api/transaksi")
def transaksi_bayar():
    """Harga dihitung ulang dari DB - klien tidak boleh menentukan harga."""
    d = request.get_json(silent=True) or {}
    items = d.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify(error="Keranjang kosong"), 400
    try:
        diskon = bilangan(d.get("diskon") or 0, "Diskon")
        pajak = bilangan(d.get("pajak") or 0, "Pajak")
        bayar = bilangan(d.get("bayar") or 0, "Bayar")
        metode = str(d.get("metode") or "Tunai")
        if metode not in ("Tunai", "QRIS", "Transfer"):
            return jsonify(error="Metode bayar tidak dikenal"), 400
        with db() as c:
            shift_aktif = c.execute(
                "SELECT id FROM shift WHERE kasir_id=%s AND tutup IS NULL", (session["kasir_id"],)
            ).fetchone()
            if not shift_aktif:
                return jsonify(error="Buka shift dulu sebelum transaksi"), 400
            resolved = []
            for it in items:
                pid = bilangan((it or {}).get("id"), "Produk", min=1)
                qty = bilangan((it or {}).get("qty"), "Qty", min=1)
                p = c.execute("SELECT * FROM produk WHERE id=%s", (pid,)).fetchone()
                if not p:
                    raise ValueError("Ada produk yang tidak ditemukan")
                if p["stok"] < qty:
                    raise ValueError(f"Stok {p['nama']} tinggal {p['stok']}")
                resolved.append((p, qty))
            subtotal = sum(p["harga"] * q for p, q in resolved)
            if diskon > subtotal:
                raise ValueError("Diskon melebihi subtotal")
            total = subtotal - diskon + pajak
            if bayar < total:
                raise ValueError(f"Bayar kurang {rupiah(total - bayar)}")
            kembalian = bayar - total
            sekarang = datetime.now()
            kunci = sekarang.strftime("%d%m%Y")
            urut = c.execute(
                """INSERT INTO nomor (kunci,nilai) VALUES (%s,1)
                   ON CONFLICT (kunci) DO UPDATE SET nilai=nomor.nilai+1 RETURNING nilai""",
                (kunci,),
            ).fetchone()["nilai"]
            no = kunci + str(urut).zfill(4)
            tid = c.execute(
                """INSERT INTO transaksi
                   (no,tanggal,subtotal,diskon,pajak,total,bayar,kembalian,metode,kasir_id,kasir_nama,shift_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (
                    no,
                    sekarang.strftime("%Y-%m-%d %H:%M:%S"),
                    subtotal,
                    diskon,
                    pajak,
                    total,
                    bayar,
                    kembalian,
                    metode,
                    session["kasir_id"],
                    session["kasir_nama"],
                    shift_aktif["id"] if shift_aktif else None,
                ),
            ).fetchone()["id"]
            for p, q in resolved:
                c.execute(
                    """INSERT INTO transaksi_item
                       (transaksi_id,produk_id,nama,harga,modal,qty,subtotal) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (tid, p["id"], p["nama"], p["harga"], p["modal"], q, p["harga"] * q),
                )
                c.execute("UPDATE produk SET stok=stok-%s WHERE id=%s", (q, p["id"]))
            if metode == "Tunai":
                c.execute(
                    """INSERT INTO kas (kasir_id,saldo) VALUES (%s,%s)
                       ON CONFLICT (kasir_id) DO UPDATE
                       SET saldo=kas.saldo+EXCLUDED.saldo, updated_at=LOCALTIMESTAMP""",
                    (session["kasir_id"], total),
                )
            tx = dict(c.execute("SELECT * FROM transaksi WHERE id=%s", (tid,)).fetchone())
            tx["items"] = [
                dict(r)
                for r in c.execute("SELECT * FROM transaksi_item WHERE transaksi_id=%s", (tid,)).fetchall()
            ]
        catat("transaksi", no)
        return jsonify(tx), 201
    except ValueError as e:
        return jsonify(error=str(e)), 400


# ---------- API dashboard ----------
@app.get("/api/dashboard")
def dashboard_data():
    hari_ini = date.today().isoformat()
    with db() as c:
        ringkas = c.execute(
            """SELECT COALESCE(SUM(total),0) penjualan, COUNT(*) jumlah
               FROM transaksi WHERE batal=false AND tanggal::date=%s""",
            (hari_ini,),
        ).fetchone()
        laba = c.execute(
            """SELECT COALESCE(SUM((ti.harga - ti.modal) * ti.qty),0) AS laba
               FROM transaksi_item ti JOIN transaksi t ON t.id=ti.transaksi_id
               WHERE NOT t.batal AND t.tanggal::date=%s""",
            (hari_ini,),
        ).fetchone()["laba"]
        terlaris = [
            dict(r)
            for r in c.execute(
                """SELECT p.nama, SUM(ti.qty) qty, SUM(ti.subtotal) omzet,
                          SUM((ti.harga - ti.modal) * ti.qty) laba
                   FROM transaksi_item ti
                   JOIN transaksi t ON t.id=ti.transaksi_id AND NOT t.batal
                   JOIN produk p ON p.id=ti.produk_id
                   GROUP BY p.id ORDER BY qty DESC LIMIT 5"""
            ).fetchall()
        ]
        tujuh_hari = []
        for i in range(6, -1, -1):
            d = (date.today() - timedelta(days=i)).isoformat()
            total = c.execute(
                "SELECT COALESCE(SUM(total),0) AS total FROM transaksi WHERE batal=false AND tanggal::date=%s", (d,)
            ).fetchone()["total"]
            tujuh_hari.append({"tanggal": d, "total": total})
        stok_menipis = c.execute("SELECT COUNT(*) AS jumlah FROM produk WHERE stok <= 10").fetchone()["jumlah"]
    return jsonify(
        penjualan=ringkas["penjualan"],
        jumlah=ringkas["jumlah"],
        laba=laba,
        terlaris=terlaris,
        tujuh_hari=tujuh_hari,
        stok_menipis=stok_menipis,
    )


if __name__ == "__main__":
    init_db()
    ssl = None
    if os.environ.get("USE_HTTPS") == "1":
        ssl = (os.path.join(BASE, "cert", "cert.pem"), os.path.join(BASE, "cert", "key.pem"))
    # host 127.0.0.1 = aman untuk lokal. Ganti 0.0.0.0 kalau mau akses dari tablet.
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False, ssl_context=ssl)
