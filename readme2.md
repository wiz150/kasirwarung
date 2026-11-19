# Panduan Pemasangan KasirWarung

Panduan ini untuk memasang aplikasi dari kosong sampai bisa dipakai kasir.
Semua perintah dijalankan sebagai user biasa (`dana`) kecuali yang diawali `sudo`.

## 1. Tools yang perlu diinstall

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip postgresql postgresql-contrib \
                    nginx openssl git curl
```

Versi minimum: Python 3.10, PostgreSQL 14. Cek dengan `python3 --version`
dan `psql --version`.

## 2. Ambil kode

```bash
git clone https://github.com/<USER>/kasirwarung.git ~/kasir
cd ~/kasir
```

Ganti `<USER>` dengan akun GitHub Anda.

## 3. Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` berisi Flask, psycopg[binary], dan gunicorn.

## 4. Siapkan PostgreSQL

Buat role dan database:

```bash
sudo -u postgres psql
```

Di dalam psql:

```sql
CREATE USER kasir WITH PASSWORD 'PASSWORD_KUAT_ANDA';
CREATE DATABASE kasir OWNER kasir;
\q
```

Simpan password yang sama ke file yang dibaca aplikasi:

```bash
printf '%s' 'PASSWORD_KUAT_ANDA' > ~/kasir/db_password.txt
chmod 600 ~/kasir/db_password.txt
```

Jangan pernah commit file ini. File ini sudah diblokir oleh `.gitignore`.

## 5. Jalankan sekali untuk inisialisasi

```bash
cd ~/kasir
.venv/bin/python app.py
```

Saat pertama jalan, aplikasi otomatis:

- membuat tabel dan 10 produk contoh;
- membuat akun `admin` dengan password acak yang ditulis ke
  `~/kasir/ADMIN_PASSWORD.txt` (mode `0600`);
- membuat `~/kasir/secret.key` (mode `0600`) untuk menandatangani session
  dan mengenkripsi backup.

Baca password admin dari file itu, buka `http://127.0.0.1:5000`, login, lalu
ganti password lewat menu **Kasir & Sesi → Reset**.

Hentikan server development dengan `Ctrl+C`. Jangan pakai `app.py` untuk produksi.

## 6. Buat sertifikat HTTPS lokal

```bash
cd ~/kasir
mkdir -p cert
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout cert/key.pem -out cert/cert.pem -days 365 \
  -subj "/CN=KasirWarung-Local" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 600 cert/key.pem
chmod 644 cert/cert.pem
```

Sertifikat self-signed akan memicu peringatan browser sekali per perangkat.
Itu wajar untuk jaringan lokal.

## 7. Pasang reverse proxy nginx

Port 80 sudah sering dipakai layanan lain, jadi konfigurasi ini memakai
`8080` (redirect HTTPS) dan `8443` (HTTPS).

```bash
sudo mkdir -p /etc/nginx/ssl
sudo cp ~/kasir/cert/cert.pem /etc/nginx/ssl/kasir_cert.pem
sudo cp ~/kasir/cert/key.pem /etc/nginx/ssl/kasir_key.pem
sudo chown root:root /etc/nginx/ssl/kasir_cert.pem /etc/nginx/ssl/kasir_key.pem
sudo chmod 644 /etc/nginx/ssl/kasir_cert.pem
sudo chmod 600 /etc/nginx/ssl/kasir_key.pem

sudo cp ~/kasir/deploy/nginx-kasir.conf /etc/nginx/sites-available/kasir
sudo ln -sf /etc/nginx/sites-available/kasir /etc/nginx/sites-enabled/kasir
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

## 8. Pasang service gunicorn

```bash
sudo cp ~/kasir/deploy/kasir.service /etc/systemd/system/kasir.service
sudo systemctl daemon-reload
sudo systemctl enable --now kasir.service
sudo systemctl status kasir.service
```

Service menjalankan gunicorn di `127.0.0.1:8000` (internal). nginx meneruskan
request ke sana. Untuk restart: `sudo systemctl restart kasir`.

## 9. Akses aplikasi

- Lokal: `https://127.0.0.1:8443`
- Tablet/WiFi: `https://IP-LAPTOP:8443`

HTTP `http://IP:8080` otomatis di-redirect ke HTTPS.

## 10. Verifikasi

```bash
cd ~/kasir
.venv/bin/python smoke_test.py
systemctl status kasir nginx postgresql
curl -k -I https://127.0.0.1:8443/login
```

`smoke_test.py` menguji halaman, CRUD produk, transaksi, validasi, dashboard,
riwayat, CSV, dan shift.

## 11. Backup & restore

Backup manual:

```bash
cd ~/kasir
.venv/bin/python backup.py
```

Hasilnya berupa `backups/kasir_YYYYMMDD_HHMMSS.dump.enc` (terenkripsi dengan
`secret.key`). Salinan offsite diatur dari menu **Kasir & Sesi → Folder offsite**
atau lewat `offsite_path.txt` berisi path absolut.

Restore ke database baru:

```bash
.venv/bin/python backup.py restore backups/NAMA.dump.enc kasir_restore
```

Jadwal harian 02:00 WIB diatur lewat cronjob Hermes `KasirWarung backup harian`
dengan script `~/.hermes/scripts/kasir_backup.py`. Cron punya `catch_up`, jadi
backup yang terlewat saat mesin mati dijalankan sekali saat mesin menyala lagi.

**Simpan `secret.key` di lokasi terpisah.** Tanpa itu dump terenkripsi tidak
bisa dipulihkan.

## 12. Catatan penting

- Jangan pernah commit `db_password.txt`, `ADMIN_PASSWORD.txt`, `secret.key`,
  `offsite_path.txt`, `cert/key.pem`, `backups/`, `logs/`, atau `*.db`.
- Semua POST/PUT/DELETE butuh CSRF token; browser mendapatkannya otomatis
  dari meta tag.
- Untuk akses dari tablet, izinkan port `8443` di firewall:
  `sudo ufw allow 8443/tcp`.
- Tailwind, Chart.js, dan Google Fonts dimuat dari CDN. Tanpa internet
  aplikasi dan data tetap jalan, hanya tampilan yang berubah.
