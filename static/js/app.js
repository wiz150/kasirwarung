/* KasirWarung - satu JS untuk semua halaman. Fungsi kecil, tanpa framework. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const rupiah = n => "Rp " + Number(n || 0).toLocaleString("id-ID");
const escapeHtml = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const waktu = s => new Date(s.replace(" ", "T")).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
const ADMIN = document.body.dataset.role === "admin";

/* Profil kertas: dipilih sekali, tersimpan di localStorage, dipakai otomatis tiap cetak. */
const PRINTER = {
  term80: { page: "80mm auto", margin: "0", lebar: "80mm", font: "12px", baris: "1.25" },
  term57: { page: "57mm auto", margin: "0", lebar: "57mm", font: "9px", baris: "1.2" },
  dot:    { page: "A4", margin: "0", lebar: "80mm", font: "10px", baris: "1.1" },
  a4:     { page: "A4", margin: "0", lebar: "80mm", font: "12px", baris: "1.25" },
};

function aturPrinter(kunci) {
  const p = PRINTER[kunci] || PRINTER.term80;
  const el = $("#struk-cetak");
  if (el) {
    el.style.setProperty("--lebar-struk", p.lebar);
    el.style.setProperty("--ukuran-struk", p.font);
    el.style.setProperty("--baris-struk", p.baris);
  }
  let style = $("#ukuran-kertas");
  if (!style) {
    style = document.createElement("style");
    style.id = "ukuran-kertas";
    document.head.append(style);
  }
  style.textContent = `@media print { @page { size: ${p.page}; margin: ${p.margin}; } }`;
}

/* Modal punya overflow-y:auto yang memotong struk saat dicetak — pindahkan ke body dulu. */
let strukDipindah = null;
window.addEventListener("beforeprint", () => {
  const el = $("#struk-cetak");
  if (!el) return;
  strukDipindah = { parent: el.parentNode, next: el.nextSibling };
  document.body.appendChild(el);
  aturPrinter(localStorage.getItem("profilPrinter") || "term80");
});
window.addEventListener("afterprint", () => {
  if (!strukDipindah) return;
  const el = $("#struk-cetak");
  if (el) {
    if (strukDipindah.next) strukDipindah.parent.insertBefore(el, strukDipindah.next);
    else strukDipindah.parent.appendChild(el);
  }
  strukDipindah = null;
});

async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.method && ["POST", "PUT", "PATCH", "DELETE"].includes(o.method.toUpperCase())) {
    const meta = document.querySelector('meta[name="csrf-token"]');
    o.headers = { "X-CSRF-Token": meta ? meta.content : "", ...(o.headers || {}) };
  }
  if (o.body && !(o.body instanceof FormData) && typeof o.body !== "string") {
    o.body = JSON.stringify(o.body);
    o.headers = { "Content-Type": "application/json", ...(o.headers || {}) };
  }
  const res = await fetch(path, o);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Gagal memproses permintaan");
  return data;
}

function toast(pesan, jenis = "sukses") {
  const warna = { sukses: "bg-emerald-600", gagal: "bg-rose-600", info: "bg-indigo-600" }[jenis] || "bg-indigo-600";
  const el = document.createElement("div");
  el.className = `${warna} text-white text-sm font-semibold px-4 py-3 rounded-xl shadow-xl transition-opacity duration-300`;
  el.textContent = pesan;
  $("#toast-host").append(el);
  setTimeout(() => { el.classList.add("opacity-0"); setTimeout(() => el.remove(), 300); }, 2600);
}

function bukaModal(isi, lebar = "max-w-lg") {
  $("#modal-root").innerHTML = `
    <div class="fixed inset-0 z-50 flex items-center justify-center p-3">
      <div class="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" data-tutup></div>
      <div class="relative bg-white rounded-2xl shadow-2xl w-full ${lebar} max-h-[92vh] overflow-y-auto">${isi}</div>
    </div>`;
  $$("#modal-root [data-tutup]").forEach(el => el.onclick = tutupModal);
}
function tutupModal() { $("#modal-root").innerHTML = ""; }

function konfirmasi(pesan) {
  return new Promise(resolve => {
    bukaModal(`
      <div class="p-6">
        <h3 class="text-lg font-extrabold text-slate-900">Konfirmasi</h3>
        <p class="text-sm text-slate-600 mt-2">${escapeHtml(pesan)}</p>
        <div class="flex justify-end gap-2 mt-6">
          <button data-tidak class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Batal</button>
          <button data-ya class="h-10 px-5 rounded-xl bg-rose-600 text-white text-sm font-bold">Ya, lanjutkan</button>
        </div>
      </div>`, "max-w-sm");
    $("#modal-root [data-ya]").onclick = () => { tutupModal(); resolve(true); };
    $("#modal-root [data-tidak]").onclick = () => { tutupModal(); resolve(false); };
  });
}

/* Struk identik untuk cetak saat bayar maupun cetak ulang dari riwayat. */
function strukHTML(tx, perluKode = false) {
  const info = window.TOKO || { nama: "KASIR WARUNG", alamat: "", telepon: "" };
  const baris = tx.items.map(i => `
    <tr><td class="py-0.5">${escapeHtml(i.nama)}</td>
        <td class="text-right py-0.5">${i.qty} × ${rupiah(i.harga)}</td>
        <td class="text-right py-0.5">${rupiah(i.subtotal)}</td></tr>`).join("");
  return `
    <div class="p-4">
      <div id="struk-cetak" class="struk mx-auto bg-white text-slate-900" style="max-width:var(--lebar-struk,80mm)">
        <div class="text-center">
          ${info.foto ? `<img src="${escapeHtml(info.foto)}" alt="" class="mx-auto h-12 object-contain mb-1">` : ""}
          <div class="text-lg font-extrabold">${escapeHtml(info.nama)}</div>
          ${info.alamat ? `<div class="text-[11px]">${escapeHtml(info.alamat)}</div>` : ""}
          ${info.telepon ? `<div class="text-[11px]">Telp: ${escapeHtml(info.telepon)}</div>` : ""}
          <div class="text-[11px]">${waktu(tx.tanggal)}</div>
        </div>
        <div class="my-2 border-t border-dashed border-slate-400"></div>
        <div class="text-[11px]">No: ${escapeHtml(tx.no)}</div>
        <div class="text-[11px]">Metode: ${escapeHtml(tx.metode || "Tunai")}</div>
        ${tx.batal ? `<div class="text-center text-sm font-extrabold text-rose-600">*** BATAL ***</div>
          ${tx.alasan_batal ? `<div class="text-[11px] text-rose-500">Alasan: ${escapeHtml(tx.alasan_batal)}</div>` : ""}` : ""}
        <div class="text-[11px]">Kasir: ${escapeHtml(tx.kasir_nama || "-")}</div>
        <div class="my-2 border-t border-dashed border-slate-400"></div>
        <table class="w-full text-[12px]"><tbody>${baris}</tbody></table>
        <div class="my-2 border-t border-dashed border-slate-400"></div>
        <table class="w-full text-[12px]">
          <tr><td>Subtotal</td><td class="text-right">${rupiah(tx.subtotal)}</td></tr>
          <tr><td>Diskon</td><td class="text-right">-${rupiah(tx.diskon)}</td></tr>
          <tr><td>Pajak</td><td class="text-right">${rupiah(tx.pajak)}</td></tr>
          <tr class="font-bold text-[14px]"><td>TOTAL</td><td class="text-right">${rupiah(tx.total)}</td></tr>
          <tr><td>Bayar</td><td class="text-right">${rupiah(tx.bayar)}</td></tr>
          <tr><td>Kembalian</td><td class="text-right">${rupiah(tx.kembalian)}</td></tr>
        </table>
        <div class="my-2 border-t border-dashed border-slate-400"></div>
        <div class="text-center text-[11px]">${escapeHtml(info.footer || "Terima kasih sudah berbelanja")}</div>
      </div>
      <div class="flex items-center justify-between gap-2 mt-4 no-print">
        <label for="jenis-printer" class="text-xs font-semibold text-slate-500">Jenis printer</label>
        <select id="jenis-printer" class="h-9 px-2 rounded-lg border border-slate-200 text-xs font-semibold outline-none">
          <option value="term80">Thermal 80mm</option>
          <option value="term57">Thermal 57mm</option>
          <option value="dot">Dot matrix 80 kolom</option>
          <option value="a4">A4 / kertas biasa</option>
        </select>
      </div>
      <div class="flex justify-end gap-2 mt-3 no-print">
        <button data-tutup class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Tutup</button>
        ${perluKode
          ? '<form id="form-kode-cetak" class="flex gap-2"><input id="kode-cetak" type="password" placeholder="Kode cetak dari admin" autocomplete="off" class="h-10 px-3 rounded-xl border border-slate-200 text-sm outline-none focus:border-indigo-400"><button class="h-10 px-4 rounded-xl bg-indigo-600 text-white text-sm font-bold">Cetak</button></form>'
          : '<button data-cetak class="h-10 px-5 rounded-xl bg-indigo-600 text-white text-sm font-bold">Cetak Struk</button>'}
      </div>
    </div>`;
}
function tampilkanStruk(tx, dariRiwayat = false) {
  const perluKode = !ADMIN && dariRiwayat;
  bukaModal(strukHTML(tx, perluKode));
  $$("#modal-root [data-tutup]").forEach(el => el.onclick = tutupModal);
  const pilih = $("#jenis-printer");
  const tersimpan = localStorage.getItem("profilPrinter") || "term80";
  pilih.value = PRINTER[tersimpan] ? tersimpan : "term80";
  const terapkan = () => {
    localStorage.setItem("profilPrinter", pilih.value);
    aturPrinter(pilih.value);
  };
  pilih.onchange = terapkan;
  terapkan();
  if (!perluKode) {
    $("#modal-root [data-cetak]").onclick = () => window.print();
  } else {
    $("#form-kode-cetak").onsubmit = async e => {
      e.preventDefault();
      try {
        await api("/api/cetak", { method: "POST", body: { kode: $("#kode-cetak").value, no: tx.no } });
        window.print();
      } catch (err) { toast(err.message, "gagal"); }
    };
  }
}

/* ---------------- Halaman Kasir ---------------- */
function pageKasir() {
  let produk = [];
  let terlihat = [];
  let audio = null;
  const keranjang = new Map(); // id -> qty
  const grid = $("#produk-grid"), cart = $("#cart-items");
  const cari = $("#cari-produk"), kategori = $("#filter-kategori");

  async function muat() {
    produk = await api("/api/produk");
    const [shift, profil] = await Promise.all([api("/api/shift"), api("/api/profil")]);
    $("#peringatan-shift").classList.toggle("hidden", shift.some(s => s.kasir_id === profil.id && s.tutup === null));
    const dipilih = kategori.value;
    kategori.innerHTML = '<option value="">Semua kategori</option>' +
      [...new Set(produk.map(p => p.kategori))].sort().map(k => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join("");
    kategori.value = dipilih;
    render();
  }

  function render() {
    const q = cari.value.trim().toLowerCase(), kat = kategori.value;
    const daftar = produk.filter(p => (!kat || p.kategori === kat) && (p.nama + " " + p.kategori + " " + (p.barcode || "")).toLowerCase().includes(q));
    terlihat = daftar;
    $("#jumlah-produk").textContent = `${daftar.length} produk`;
    grid.innerHTML = daftar.length ? daftar.map(p => {
      const gambar = p.gambar
        ? `<img src="${escapeHtml(p.gambar)}" alt="" class="w-full h-24 object-cover rounded-xl">`
        : `<div class="w-full h-24 rounded-xl bg-gradient-to-br from-indigo-100 to-violet-100 grid place-items-center text-3xl font-extrabold text-indigo-300">${escapeHtml(p.nama.charAt(0))}</div>`;
      return `<article class="bg-white rounded-2xl border border-slate-100 shadow-sm p-3 card-hover">
        ${gambar}
        <div class="mt-2 flex items-start justify-between gap-2">
          <h3 class="font-bold text-sm text-slate-900 leading-tight line-clamp-2">${escapeHtml(p.nama)}</h3>
          <span class="shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">${escapeHtml(p.kategori)}</span>
        </div>
        <div class="flex items-center justify-between mt-2">
          <span class="font-extrabold text-indigo-600 text-sm">${rupiah(p.harga)}</span>
          <span class="text-[11px] font-semibold ${p.stok <= 10 ? "text-rose-500" : "text-slate-400"}">Stok ${p.stok}${p.stok > 0 && p.stok <= 10 ? ' <span class="bg-rose-50 px-1.5 py-0.5 rounded-full">Tipis</span>' : ""}</span>
        </div>
        <button data-tambah="${p.id}" ${p.stok < 1 ? "disabled" : ""} class="w-full h-9 mt-3 rounded-xl text-sm font-bold transition duration-150 ${p.stok < 1 ? "bg-slate-100 text-slate-400" : "bg-indigo-50 text-indigo-700 hover:bg-indigo-600 hover:text-white"}">
          ${p.stok < 1 ? "Stok habis" : "+ Tambah"}
        </button>
      </article>`;
    }).join("") : `<p class="col-span-full text-center text-sm text-slate-400 py-12">Produk tidak ditemukan.</p>`;
    $$("[data-tambah]", grid).forEach(b => b.onclick = () => tambah(Number(b.dataset.tambah)));
    renderCart();
  }

  function beep() {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === "suspended") audio.resume();
      const o = audio.createOscillator(), g = audio.createGain();
      o.type = "sine"; o.frequency.value = 880;
      g.gain.setValueAtTime(0.08, audio.currentTime);
      g.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.07);
      o.connect(g); g.connect(audio.destination);
      o.start(); o.stop(audio.currentTime + 0.07);
    } catch (err) { /* audio tidak tersedia: diamkan */ }
  }

  function tambah(id) {
    const p = produk.find(x => x.id === id);
    const q = keranjang.get(id) || 0;
    if (q >= p.stok) return toast("Stok tidak cukup", "gagal");
    keranjang.set(id, q + 1);
    renderCart();
  }

  function renderCart() {
    if (!keranjang.size) {
      cart.innerHTML = `<div class="text-center py-10 px-4"><div class="text-4xl">🧺</div><p class="text-sm text-slate-400 mt-2">Keranjang masih kosong</p></div>`;
    } else {
      cart.innerHTML = [...keranjang].map(([id, qty]) => {
        const p = produk.find(x => x.id === id);
        return `<div class="flex items-center gap-3 p-2 rounded-xl hover:bg-slate-50 transition duration-150">
          <div class="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-600 grid place-items-center font-extrabold text-sm">${escapeHtml(p.nama.charAt(0))}</div>
          <div class="min-w-0 flex-1">
            <div class="text-sm font-semibold text-slate-800 truncate">${escapeHtml(p.nama)}</div>
            <div class="text-xs text-slate-500">${rupiah(p.harga)}</div>
          </div>
          <div class="flex items-center gap-1">
            <button data-kurang="${id}" class="w-7 h-7 rounded-lg bg-slate-100 font-bold text-slate-600 hover:bg-slate-200">−</button>
            <span class="w-6 text-center text-sm font-bold">${qty}</span>
            <button data-tambah2="${id}" class="w-7 h-7 rounded-lg bg-indigo-50 font-bold text-indigo-600 hover:bg-indigo-100">+</button>
          </div>
          <button data-hapus="${id}" class="text-slate-300 hover:text-rose-500 transition duration-150" aria-label="Hapus">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18" stroke-linecap="round"/></svg>
          </button>
        </div>`;
      }).join("");
      $$("[data-kurang]", cart).forEach(b => b.onclick = () => {
        const id = Number(b.dataset.kurang);
        if (keranjang.get(id) <= 1) keranjang.delete(id); else keranjang.set(id, keranjang.get(id) - 1);
        renderCart();
      });
      $$("[data-tambah2]", cart).forEach(b => b.onclick = () => tambah(Number(b.dataset.tambah2)));
      $$("[data-hapus]", cart).forEach(b => b.onclick = () => { keranjang.delete(Number(b.dataset.hapus)); renderCart(); });
    }
    hitung();
  }

  function hitung() {
    const subtotal = [...keranjang].reduce((s, [id, q]) => s + (produk.find(p => p.id === id)?.harga || 0) * q, 0);
    const diskon = Math.max(0, Number($("#diskon").value) || 0);
    const pajak = Math.max(0, Number($("#pajak").value) || 0);
    const bayar = Number($("#bayar").value) || 0;
    const total = Math.max(0, subtotal - diskon + pajak);
    $("#subtotal").textContent = rupiah(subtotal);
    $("#total").textContent = rupiah(total);
    $("#kembalian").textContent = bayar ? rupiah(bayar - total) : "Rp 0";
    $("#kembalian").classList.toggle("text-rose-600", bayar > 0 && bayar < total);
    $("#cart-count").textContent = `${[...keranjang.values()].reduce((a, b) => a + b, 0)} item`;
    $("#btn-bayar").disabled = !keranjang.size || bayar < total;
  }

  async function bayar() {
    try {
      const tx = await api("/api/transaksi", {
        method: "POST",
        body: {
          items: [...keranjang].map(([id, qty]) => ({ id, qty })),
          diskon: Number($("#diskon").value) || 0,
          pajak: Number($("#pajak").value) || 0,
          bayar: Number($("#bayar").value) || 0,
          metode: $("#metode").value,
        },
      });
      keranjang.clear();
      $("#diskon").value = 0; $("#pajak").value = 0; $("#bayar").value = "";
      await muat();
      tampilkanStruk(tx);
      toast("Transaksi berhasil disimpan");
    } catch (e) { toast(e.message, "gagal"); }
  }

  cari.oninput = render;
  kategori.onchange = render;
  $("#btn-buka-shift").onclick = bukaShiftModal;
  $("#scan-barcode").onkeydown = e => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const kode = e.target.value.trim().toLowerCase();
    const p = !kode ? null : produk.find(x => (x.barcode || "").toLowerCase() === kode);
    if (p) { tambah(p.id); beep(); }
    else toast("Barcode tidak ditemukan", "gagal");
    e.target.value = "";
    e.target.focus();
  };
  document.addEventListener("keydown", e => {
    if ($("#modal-root").children.length) return;
    const tag = (e.target.tagName || "").toLowerCase();
    const mengetik = ["input", "textarea", "select"].includes(tag);
    if (e.key === "F2") { e.preventDefault(); $("#scan-barcode").focus(); return; }
    if (e.key === "Escape" && !mengetik) { $("#btn-kosongkan").click(); return; }
    if (e.key === "F9") { e.preventDefault(); if (!$("#btn-bayar").disabled) bayar(); return; }
    if (/^[1-9]$/.test(e.key) && !mengetik) {
      const p = terlihat[Number(e.key) - 1];
      if (p) { tambah(p.id); beep(); }
    }
  });
  ["diskon", "pajak", "bayar"].forEach(id => $("#" + id).oninput = hitung);
  $("#btn-kosongkan").onclick = () => { keranjang.clear(); renderCart(); };
  $("#btn-bayar").onclick = bayar;
  muat();
}

/* ---------------- Halaman Produk ---------------- */
function pageProduk() {
  let semua = [];
  const tbody = $("#tabel-produk");

  async function muat() {
    semua = await api("/api/produk");
    const q = $("#cari-produk").value.trim().toLowerCase();
    const daftar = semua.filter(p => (p.nama + " " + p.kategori + " " + (p.barcode || "")).toLowerCase().includes(q));
    $("#info-produk").textContent = `${daftar.length} dari ${semua.length} produk`;
    tbody.innerHTML = daftar.length ? daftar.map(p => `
      <tr>
        <td class="px-5 py-3">
          <div class="flex items-center gap-3">
            ${p.gambar ? `<img src="${escapeHtml(p.gambar)}" class="w-10 h-10 rounded-lg object-cover" alt="">` : `<div class="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-600 grid place-items-center font-extrabold">${escapeHtml(p.nama.charAt(0))}</div>`}
            <div><div class="font-semibold text-slate-800">${escapeHtml(p.nama)}</div><div class="text-xs text-slate-400">#${p.id}</div></div>
          </div>
        </td>
        <td class="px-4 py-3"><span class="text-xs font-semibold bg-slate-100 text-slate-600 px-2 py-1 rounded-full">${escapeHtml(p.kategori)}</span></td>
        <td class="px-4 py-3 text-right font-semibold">${rupiah(p.harga)}<div class="text-[10px] font-normal text-slate-400">modal ${rupiah(p.modal || 0)}</div></td>
        <td class="px-4 py-3 text-center"><span class="text-xs font-bold px-2.5 py-1 rounded-full ${p.stok === 0 ? "bg-rose-50 text-rose-600" : p.stok <= 10 ? "bg-amber-50 text-amber-600" : "bg-emerald-50 text-emerald-600"}">${p.stok}</span></td>
        <td class="px-5 py-3 text-right">
          <button data-edit="${p.id}" class="text-xs font-bold text-indigo-600 hover:underline">Edit</button>
          <button data-opname="${p.id}" class="ml-3 text-xs font-bold text-amber-600 hover:underline">Opname</button>
          <button data-hapus="${p.id}" class="ml-3 text-xs font-bold text-rose-500 hover:underline">Hapus</button>
        </td>
      </tr>`).join("") : `<tr><td colspan="5" class="text-center text-sm text-slate-400 py-12">Belum ada produk.</td></tr>`;
    $$("[data-edit]", tbody).forEach(b => b.onclick = () => formProduk(semua.find(p => p.id === Number(b.dataset.edit))));
    $$("[data-opname]", tbody).forEach(b => b.onclick = () => formOpname(semua.find(p => p.id === Number(b.dataset.opname))));
    $$("[data-hapus]", tbody).forEach(b => b.onclick = async () => {
      if (!await konfirmasi("Hapus produk ini? Riwayat transaksi tetap tersimpan.")) return;
      try { await api("/api/produk/" + b.dataset.hapus, { method: "DELETE" }); toast("Produk dihapus"); muat(); }
      catch (e) { toast(e.message, "gagal"); }
    });
  }

  function formOpname(p) {
    bukaModal(`
      <form id="form-opname" class="p-6">
        <h3 class="text-lg font-extrabold text-slate-900 mb-4">Stok opname · ${escapeHtml(p.nama)}</h3>
        <p class="text-xs text-slate-500 mb-3">Stok saat ini: <b>${p.stok}</b>. Isi jumlah hasil hitungan fisik.</p>
        <label class="block text-xs font-bold text-slate-500 mb-1">Stok baru</label>
        <input name="stok" type="number" min="0" required value="${p.stok}" class="w-full h-10 mb-3 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400">
        <label class="block text-xs font-bold text-slate-500 mb-1">Alasan</label>
        <input name="alasan" value="opname" class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400">
        <div class="flex justify-end gap-2 mt-6">
          <button type="button" data-tutup class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Batal</button>
          <button class="h-10 px-5 rounded-xl bg-amber-500 text-white text-sm font-bold">Simpan stok</button>
        </div>
      </form>`, "max-w-sm");
    $("#modal-root [data-tutup]").onclick = tutupModal;
    $("#form-opname").onsubmit = async e => {
      e.preventDefault();
      try {
        await api(`/api/produk/${p.id}/stok`, { method: "POST", body: Object.fromEntries(new FormData(e.target)) });
        tutupModal(); toast("Stok disesuaikan"); muat();
      } catch (err) { toast(err.message, "gagal"); }
    };
  }

  function formProduk(p = {}) {
    bukaModal(`
      <form id="form-produk" class="p-6">
        <h3 class="text-lg font-extrabold text-slate-900 mb-4">${p.id ? "Edit produk" : "Produk baru"}</h3>
        <label class="block text-xs font-bold text-slate-500 mb-1">Nama</label>
        <input name="nama" required value="${escapeHtml(p.nama || "")}" class="w-full h-10 mb-3 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50">
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-xs font-bold text-slate-500 mb-1">Harga (Rp)</label>
            <input name="harga" type="number" min="0" required value="${p.harga ?? 0}" class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50"></div>
          <div><label class="block text-xs font-bold text-slate-500 mb-1">Stok</label>
            <input name="stok" type="number" min="0" required value="${p.stok ?? 0}" class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50"></div>
        </div>
        <label class="block text-xs font-bold text-slate-500 mb-1 mt-3">Harga modal (Rp)</label>
        <input name="modal" type="number" min="0" required value="${p.modal ?? 0}" class="w-full h-10 mb-3 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50">
        <label class="block text-xs font-bold text-slate-500 mb-1">Kategori</label>
        <input name="kategori" value="${escapeHtml(p.kategori || "Umum")}" class="w-full h-10 mb-3 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50">
        <label class="block text-xs font-bold text-slate-500 mb-1">Barcode (opsional)</label>
        <input name="barcode" value="${escapeHtml(p.barcode || "")}" class="w-full h-10 mb-3 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50">
        <input type="hidden" name="gambar" value="${escapeHtml(p.gambar || "")}">
        <label class="block text-xs font-bold text-slate-500 mb-1">Gambar produk (opsional)</label>
        <input name="file_gambar" type="file" accept="image/jpeg,image/png,image/gif,image/webp" class="w-full text-xs text-slate-500 file:mr-3 file:px-3 file:py-2 file:rounded-lg file:border-0 file:bg-indigo-50 file:text-indigo-700 file:font-bold">
        <div class="flex justify-end gap-2 mt-6">
          <button type="button" data-tutup class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Batal</button>
          <button class="h-10 px-5 rounded-xl bg-indigo-600 text-white text-sm font-bold">Simpan</button>
        </div>
      </form>`);
    $("#modal-root [data-tutup]").onclick = tutupModal;
    $("#form-produk").onsubmit = async e => {
      e.preventDefault();
      const d = new FormData(e.target);
      try {
        await api(p.id ? "/api/produk/" + p.id : "/api/produk", {
          method: p.id ? "PUT" : "POST", body: d,
        });
        tutupModal(); toast("Produk disimpan"); muat();
      } catch (err) { toast(err.message, "gagal"); }
    };
  }

  $("#btn-tambah").onclick = () => formProduk();
  $("#cari-produk").oninput = muat;
  $("#btn-import").onclick = () => $("#file-csv").click();
  $("#file-csv").onchange = async e => {
    const f = e.target.files[0];
    if (!f) return;
    const fd = new FormData(); fd.append("file", f);
    try {
      const r = await api("/api/produk/import", { method: "POST", body: fd });
      toast(`${r.imported} produk diimpor`); muat();
    } catch (err) { toast(err.message, "gagal"); }
    e.target.value = "";
  };
  muat();
}

/* ---------------- Halaman Riwayat ---------------- */
function pageRiwayat() {
  const tbody = $("#tabel-riwayat");
  const BATAS = 25;
  let offset = 0;
  function baris(t) {
    return `<tr>
      <td class="px-5 py-3 font-semibold text-slate-800">${escapeHtml(t.no)}${t.batal ? '<span class="ml-2 text-[10px] font-bold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-full">BATAL</span>' : ""}</td>
      <td class="px-4 py-3 text-slate-500 text-xs">${escapeHtml(t.kasir_nama || "-")}</td>
      <td class="px-4 py-3 text-xs font-semibold text-slate-600">${escapeHtml(t.metode || "Tunai")}</td>
      <td class="px-4 py-3 text-slate-500 text-xs">${waktu(t.tanggal)}</td>
      <td class="px-4 py-3 text-slate-500">${t.items.reduce((s, i) => s + i.qty, 0)} item</td>
      <td class="px-4 py-3 text-right font-bold">${rupiah(t.total)}</td>
      <td class="px-5 py-3 text-right"><button data-detail="${t.id}" class="text-xs font-bold text-indigo-600 hover:underline">${ADMIN ? "Detail &amp; Cetak" : "Detail"}</button>${ADMIN && !t.batal ? '<button data-batal="' + t.id + '" class="ml-3 text-xs font-bold text-rose-500 hover:underline">Batal</button>' : ""}</td>
    </tr>`;
  }
  function pasangAksi() {
    $$("[data-detail]", tbody).forEach(b => b.onclick = async () => {
      try { tampilkanStruk(await api("/api/transaksi/" + b.dataset.detail), true); }
      catch (e) { toast(e.message, "gagal"); }
    });
    $$("[data-batal]", tbody).forEach(b => b.onclick = () => {
      bukaModal(`
        <form id="form-batal" class="p-6">
          <h3 class="text-lg font-extrabold text-slate-900">Batalkan transaksi</h3>
          <p class="text-sm text-slate-500 mt-1">Stok barang akan dikembalikan. Alasan wajib dicatat di Audit.</p>
          <label class="block text-xs font-bold text-slate-500 mt-4 mb-1">Alasan pembatalan</label>
          <textarea name="alasan" required minlength="3" rows="3" class="w-full px-3 py-2 rounded-xl border border-slate-200 outline-none focus:border-rose-400"></textarea>
          <div class="flex justify-end gap-2 mt-6">
            <button type="button" data-tutup class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Batal</button>
            <button class="h-10 px-5 rounded-xl bg-rose-600 text-white text-sm font-bold">Ya, batalkan</button>
          </div>
        </form>`, "max-w-sm");
      $("#modal-root [data-tutup]").onclick = tutupModal;
      $("#form-batal").onsubmit = async e => {
        e.preventDefault();
        try {
          await api(`/api/transaksi/${b.dataset.batal}/batal`, { method: "POST", body: Object.fromEntries(new FormData(e.target)) });
          tutupModal(); toast("Transaksi dibatalkan"); muat();
        } catch (err) { toast(err.message, "gagal"); }
      };
    });
  }
  async function ambil(append = false) {
    const q = new URLSearchParams({ dari: $("#dari").value, sampai: $("#sampai").value, limit: BATAS, offset: append ? offset : 0 });
    const res = await fetch("/api/transaksi?" + q);
    const daftar = await res.json().catch(() => []);
    if (!res.ok) throw new Error(daftar.error || "Gagal memuat riwayat");
    $("#total-filter").textContent = rupiah(Number(res.headers.get("X-Subtotal") || 0));
    const html = daftar.map(baris).join("");
    if (append) tbody.insertAdjacentHTML("beforeend", html);
    else tbody.innerHTML = html || `<tr><td colspan="7" class="text-center text-sm text-slate-400 py-12">Belum ada transaksi.</td></tr>`;
    pasangAksi();
    offset = (append ? offset : 0) + daftar.length;
    $("#btn-lebih").classList.toggle("hidden", daftar.length < BATAS);
  }
  async function muat() { offset = 0; await ambil(false); }
  $("#btn-lebih").onclick = () => ambil(true).catch(e => toast(e.message, "gagal"));
  $("#btn-filter").onclick = muat;
  $("#btn-reset").onclick = () => { $("#dari").value = ""; $("#sampai").value = ""; muat(); };
  if ($("#btn-export-riwayat")) {
    $("#btn-export-riwayat").onclick = () => {
      const q = new URLSearchParams({ dari: $("#dari").value, sampai: $("#sampai").value });
      window.location.href = "/api/transaksi/export?" + q;
    };
  }
  muat();
}

/* ---------------- Halaman Dashboard ---------------- */
function pageDashboard() {
  const warna = ["bg-indigo-500", "bg-violet-500", "bg-sky-500", "bg-emerald-500", "bg-amber-500"];
  api("/api/dashboard").then(d => {
    $("#stat-penjualan").textContent = rupiah(d.penjualan);
    $("#stat-jumlah").textContent = d.jumlah;
    $("#stat-laba").textContent = rupiah(d.laba);
    $("#stat-stok").textContent = d.stok_menipis;
    $("#stat-terlaris").textContent = d.terlaris.length ? d.terlaris[0].nama.split(" ")[0] : "-";
    $("#daftar-terlaris").innerHTML = d.terlaris.length ? d.terlaris.map((p, i) => `
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg ${warna[i]} text-white grid place-items-center text-xs font-extrabold">${i + 1}</div>
        <div class="min-w-0 flex-1"><div class="text-sm font-semibold truncate">${escapeHtml(p.nama)}</div>
          <div class="text-[11px] text-slate-400">${rupiah(p.omzet)} · laba ${rupiah(p.laba || 0)}</div></div>
        <span class="text-sm font-extrabold text-slate-700">${p.qty}×</span>
      </div>`).join("") : `<p class="text-sm text-slate-400">Belum ada penjualan.</p>`;

    if (typeof Chart === "undefined") return; // CDN gagal: angka di atas tetap tampil.
    const label = d.tujuh_hari.map(x => new Date(x.tanggal + "T00:00:00").toLocaleDateString("id-ID", { weekday: "short" }));
    new Chart($("#grafik"), {
      type: "bar",
      data: { labels: label, datasets: [{ data: d.tujuh_hari.map(x => x.total), backgroundColor: "#6366f1", borderRadius: 10, maxBarThickness: 46 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { callback: v => "Rp " + (v / 1000) + "rb" } }, x: { grid: { display: false } } } },
    });
  }).catch(e => toast(e.message, "gagal"));
}

/* ---------------- Halaman Kasir & Sesi (admin) ---------------- */
function pageAkun() {
  let shiftRows = [];
  async function muat() {
    try {
      const daftar = await api("/api/kasir");
      const tbody = $("#tabel-akun");
      tbody.innerHTML = daftar.length ? daftar.map(k => `
        <tr>
          <td class="px-5 py-3 font-semibold text-slate-800">${escapeHtml(k.username)}</td>
          <td class="px-4 py-3 text-slate-600">${escapeHtml(k.nama)}</td>
          <td class="px-4 py-3 text-xs font-bold ${k.role === "admin" ? "text-indigo-600" : "text-slate-500"}">${k.role === "admin" ? "Admin" : "Kasir"}</td>
          <td class="px-4 py-3"><span class="text-xs font-bold px-2.5 py-1 rounded-full ${k.aktif && k.online ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-500"}">${!k.aktif ? "Nonaktif" : k.online ? "Sedang digunakan" : "Offline"}</span></td>
          <td class="px-5 py-3 text-xs text-slate-400">${escapeHtml(k.terakhir || "-")}</td>
          <td class="px-4 py-3 text-right text-xs font-bold text-emerald-700">${rupiah(k.saldo || 0)}</td>
          <td class="px-5 py-3 text-right whitespace-nowrap">
            <button data-saldo-akun="${k.id}" class="text-xs font-bold text-emerald-600 hover:underline">Atur kas</button>
            <button data-edit-akun="${k.id}" class="ml-2 text-xs font-bold text-indigo-600 hover:underline">Edit</button>
            <button data-reset-akun="${k.id}" class="ml-2 text-xs font-bold text-slate-600 hover:underline">Reset</button>
            <button data-aktif-akun="${k.id}" data-aktif="${k.aktif}" class="ml-2 text-xs font-bold ${k.aktif ? "text-amber-600" : "text-emerald-600"} hover:underline">${k.aktif ? "Nonaktifkan" : "Aktifkan"}</button>
            <button data-hapus-akun="${k.id}" class="ml-2 text-xs font-bold text-rose-500 hover:underline">Hapus</button>
          </td>
        </tr>`).join("") : `<tr><td colspan="7" class="text-center text-sm text-slate-400 py-12">Belum ada kasir.</td></tr>`;
      const cari = id => daftar.find(k => k.id === Number(id));
      $$("[data-saldo-akun]", tbody).forEach(b => b.onclick = () => formSaldo(cari(b.dataset.saldoAkun)));
      $$("[data-edit-akun]", tbody).forEach(b => b.onclick = () => formEditAkun(cari(b.dataset.editAkun)));
      $$("[data-reset-akun]", tbody).forEach(b => b.onclick = () => formResetAkun(cari(b.dataset.resetAkun)));
      $$("[data-aktif-akun]", tbody).forEach(b => b.onclick = async () => {
        try {
          await api(`/api/kasir/${b.dataset.aktifAkun}/aktif`, { method: "POST", body: { aktif: b.dataset.aktif !== "true" } });
          toast("Status akun diubah"); muat();
        } catch (err) { toast(err.message, "gagal"); }
      });
      $$("[data-hapus-akun]", tbody).forEach(b => b.onclick = async () => {
        const k = cari(b.dataset.hapusAkun);
        if (!await konfirmasi(`Hapus akun ${k.username}?`)) return;
        try {
          await api(`/api/kasir/${b.dataset.hapusAkun}`, { method: "DELETE" });
          toast("Akun dihapus"); muat();
        } catch (err) { toast(err.message, "gagal"); }
      });
    } catch (e) { toast(e.message, "gagal"); }
  }
  function formAkun() {
    bukaModal(`
      <form id="form-akun" class="p-6">
        <h3 class="text-lg font-extrabold text-slate-900 mb-4">Kasir baru</h3>
        <label class="block text-xs font-bold text-slate-500 mb-1">Username</label>
        <input name="username" required autocomplete="off" class="w-full h-10 mb-3 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50">
        <label class="block text-xs font-bold text-slate-500 mb-1">Nama</label>
        <input name="nama" required class="w-full h-10 mb-3 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50">
        <label class="block text-xs font-bold text-slate-500 mb-1">Password (min. 6 karakter)</label>
        <input name="password" type="password" minlength="6" required autocomplete="new-password" class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50">
        <div class="flex justify-end gap-2 mt-6">
          <button type="button" data-tutup class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Batal</button>
          <button class="h-10 px-5 rounded-xl bg-indigo-600 text-white text-sm font-bold">Simpan</button>
        </div>
      </form>`, "max-w-sm");
    $("#modal-root [data-tutup]").onclick = tutupModal;
    $("#form-akun").onsubmit = async e => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(e.target));
      try {
        await api("/api/kasir", { method: "POST", body: d });
        tutupModal(); toast("Kasir ditambahkan"); muat();
      } catch (err) { toast(err.message, "gagal"); }
    };
  }
  function formSaldo(k) {
    bukaModal(`
      <form id="form-saldo" class="p-6">
        <h3 class="text-lg font-extrabold text-slate-900 mb-4">Atur saldo kas · ${escapeHtml(k.nama)}</h3>
        <p class="text-xs text-slate-500 mb-3">Saldo sekarang: <b>${rupiah(k.saldo || 0)}</b>. Isi nilai absolut hasil hitungan fisik.</p>
        <label class="block text-xs font-bold text-slate-500 mb-1">Saldo baru (Rp)</label>
        <input name="saldo" type="number" min="0" required value="${k.saldo || 0}" class="w-full h-10 mb-3 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400">
        <label class="block text-xs font-bold text-slate-500 mb-1">Alasan</label>
        <input name="alasan" value="penyesuaian" class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400">
        <div class="flex justify-end gap-2 mt-6">
          <button type="button" data-tutup class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Batal</button>
          <button class="h-10 px-5 rounded-xl bg-emerald-600 text-white text-sm font-bold">Simpan</button>
        </div>
      </form>`, "max-w-sm");
    $("#modal-root [data-tutup]").onclick = tutupModal;
    $("#form-saldo").onsubmit = async e => {
      e.preventDefault();
      try {
        await api(`/api/kas/${k.id}`, { method: "POST", body: Object.fromEntries(new FormData(e.target)) });
        tutupModal(); toast("Saldo kas disimpan"); muat();
      } catch (err) { toast(err.message, "gagal"); }
    };
  }
  function formEditAkun(k) {
    bukaModal(`
      <form id="form-edit-akun" class="p-6">
        <h3 class="text-lg font-extrabold text-slate-900 mb-4">Edit akun ${escapeHtml(k.username)}</h3>
        <label class="block text-xs font-bold text-slate-500 mb-1">Nama</label>
        <input name="nama" required value="${escapeHtml(k.nama)}" class="w-full h-10 mb-3 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400">
        <label class="block text-xs font-bold text-slate-500 mb-1">Role</label>
        <select name="role" class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400">
          <option value="kasir" ${k.role === "kasir" ? "selected" : ""}>Kasir</option>
          <option value="admin" ${k.role === "admin" ? "selected" : ""}>Admin</option>
        </select>
        <div class="flex justify-end gap-2 mt-6">
          <button type="button" data-tutup class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Batal</button>
          <button class="h-10 px-5 rounded-xl bg-indigo-600 text-white text-sm font-bold">Simpan</button>
        </div>
      </form>`, "max-w-sm");
    $("#modal-root [data-tutup]").onclick = tutupModal;
    $("#form-edit-akun").onsubmit = async e => {
      e.preventDefault();
      try {
        await api(`/api/kasir/${k.id}`, { method: "PUT", body: Object.fromEntries(new FormData(e.target)) });
        tutupModal(); toast("Akun diubah"); muat();
      } catch (err) { toast(err.message, "gagal"); }
    };
  }
  function formResetAkun(k) {
    bukaModal(`
      <form id="form-reset-akun" class="p-6">
        <h3 class="text-lg font-extrabold text-slate-900 mb-4">Reset password ${escapeHtml(k.username)}</h3>
        <label class="block text-xs font-bold text-slate-500 mb-1">Password baru (min. 6 karakter)</label>
        <input name="password" type="password" minlength="6" required autocomplete="new-password" class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400">
        <div class="flex justify-end gap-2 mt-6">
          <button type="button" data-tutup class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Batal</button>
          <button class="h-10 px-5 rounded-xl bg-indigo-600 text-white text-sm font-bold">Simpan</button>
        </div>
      </form>`, "max-w-sm");
    $("#modal-root [data-tutup]").onclick = tutupModal;
    $("#form-reset-akun").onsubmit = async e => {
      e.preventDefault();
      try {
        await api(`/api/kasir/${k.id}/reset`, { method: "POST", body: Object.fromEntries(new FormData(e.target)) });
        tutupModal(); toast("Password direset");
      } catch (err) { toast(err.message, "gagal"); }
    };
  }
  async function muatAudit() {
    try {
      const rows = await api("/api/audit");
      $("#tabel-audit").innerHTML = rows.length ? rows.map(a => `
        <tr><td class="px-5 py-3 text-xs text-slate-400">${escapeHtml(a.waktu)}</td>
            <td class="px-4 py-3 text-slate-600">${escapeHtml(a.kasir)}</td>
            <td class="px-4 py-3 text-xs font-bold text-slate-700">${escapeHtml(a.aksi)}</td>
            <td class="px-5 py-3 text-xs text-slate-500">${escapeHtml(a.detail)}</td></tr>`).join("")
        : `<tr><td colspan="4" class="text-center text-sm text-slate-400 py-12">Belum ada aktivitas.</td></tr>`;
    } catch (err) { toast(err.message, "gagal"); }
  }
  async function muatShift() {
    try {
      const rows = await api("/api/shift");
      shiftRows = rows;
      $("#tabel-shift").innerHTML = rows.length ? rows.map(s => `
        <tr><td class="px-5 py-3 text-slate-600">${escapeHtml(s.kasir)}</td>
            <td class="px-4 py-3 text-xs text-slate-400">${escapeHtml(s.buka)}</td>
            <td class="px-4 py-3 text-xs text-slate-400">${s.tutup ? escapeHtml(s.tutup) : "<span class='text-indigo-600 font-bold'>Aktif</span>"}</td>
            <td class="px-4 py-3 text-right">${rupiah(s.awal)}</td>
            <td class="px-4 py-3 text-right">${rupiah(s.tunai)}</td>
            <td class="px-4 py-3 text-right">${s.akhir === null ? "-" : rupiah(s.akhir)}</td>
            <td class="px-5 py-3 text-right font-bold ${s.selisih === null ? "text-slate-400" : s.selisih === 0 ? "text-emerald-600" : "text-rose-600"}">${s.selisih === null ? "-" : rupiah(s.selisih)}${s.tutup ? "" : ` <button data-tutup-shift="${s.id}" class="ml-2 text-[11px] font-bold text-rose-500 hover:underline">Tutup</button>`}</td></tr>`).join("")
        : `<tr><td colspan="7" class="text-center text-sm text-slate-400 py-12">Belum ada shift.</td></tr>`;
      $$("[data-tutup-shift]", $("#tabel-shift")).forEach(b => b.onclick = () => {
        const s = shiftRows.find(x => x.id === Number(b.dataset.tutupShift));
        if (s) formTutupShiftAdmin(s);
      });
    } catch (err) { toast(err.message, "gagal"); }
  }
  async function formTutupShiftAdmin(s) {
    bukaModal(`
      <form id="form-admin-tutup-shift" class="p-6">
        <h3 class="text-lg font-extrabold text-slate-900">Tutup shift ${escapeHtml(s.kasir)}</h3>
        <p class="text-xs text-slate-500 mt-1">Mulai ${escapeHtml(s.buka)} · tunai ${rupiah(s.tunai)}</p>
        <label class="block text-xs font-bold text-slate-500 mt-4 mb-1">Uang akhir (hitung fisik)</label>
        <input name="akhir" type="number" min="0" required class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none">
        <label class="block text-xs font-bold text-slate-500 mt-3 mb-1">Catatan</label>
        <input name="catatan" class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none">
        <div class="flex justify-end gap-2 mt-6">
          <button type="button" data-tutup class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Batal</button>
          <button class="h-10 px-5 rounded-xl bg-rose-600 text-white text-sm font-bold">Tutup shift</button>
        </div>
      </form>`, "max-w-sm");
    $("#modal-root [data-tutup]").onclick = tutupModal;
    $("#form-admin-tutup-shift").onsubmit = async e => {
      e.preventDefault();
      try {
        await api(`/api/shift/${s.id}/admin-tutup`, { method: "POST", body: Object.fromEntries(new FormData(e.target)) });
        tutupModal(); toast("Shift ditutup"); muatAudit(); muatShift();
      } catch (err) { toast(err.message, "gagal"); }
    };
  }
  async function muatBackup() {
    try {
      const s = await api("/api/backup");
      $("#pilih-dump").innerHTML = s.files.length
        ? s.files.map(f => `<option value="${escapeHtml(f.nama)}">${escapeHtml(f.nama)} (${Math.round(f.ukuran / 1024)} KB)</option>`).join("")
        : '<option value="">Belum ada dump</option>';
      $("#status-backup").textContent = `${s.files.length} dump tersedia`;
      $("#offsite-path").value = s.offsite || "";
      $("#status-offsite").textContent = s.offsite ? `Offsite: ${s.offsite}` : "Belum dikonfigurasi";
    } catch (err) { toast(err.message, "gagal"); }
  }
  $("#btn-backup-now").onclick = async () => {
    try {
      await api("/api/backup", { method: "POST" });
      toast("Backup selesai"); muatBackup();
    } catch (err) { toast(err.message, "gagal"); }
  };
  $("#btn-simpan-offsite").onclick = async () => {
    try {
      await api("/api/backup/offsite", { method: "POST", body: { path: $("#offsite-path").value } });
      toast("Path offsite disimpan"); muatBackup();
    } catch (err) { toast(err.message, "gagal"); }
  };
  $("#btn-restore").onclick = async () => {
    const file = $("#pilih-dump").value, db = $("#nama-db-restore").value.trim();
    if (!file || !db) return toast("Pilih dump dan isi nama database", "gagal");
    if (!await konfirmasi(`Pulihkan ${file} ke database baru "${db}"?`)) return;
    try {
      await api("/api/restore", { method: "POST", body: { file, db } });
      toast("Restore selesai"); $("#nama-db-restore").value = "";
    } catch (err) { toast(err.message, "gagal"); }
  };
  $("#btn-tambah-akun").onclick = formAkun;
  $("#btn-refresh-akun").onclick = () => { muat(); muatAudit(); muatShift(); muatBackup(); };
  async function muatKode() {
    try {
      const s = await api("/api/kode-cetak");
      $("#status-kode").textContent = s.sudah_ada ? "Kode sudah diset" : "Belum ada kode";
    } catch (err) { toast(err.message, "gagal"); }
  }
  $("#btn-simpan-kode").onclick = async () => {
    try {
      await api("/api/kode-cetak", { method: "POST", body: { kode: $("#kode-cetak-admin").value } });
      $("#kode-cetak-admin").value = "";
      toast("Kode cetak disimpan"); muatKode();
    } catch (err) { toast(err.message, "gagal"); }
  };
  muatKode();
  muat();
  muatAudit();
  muatShift();
  muatBackup();
  setInterval(muat, 15000);
}

/* ---------------- Halaman Pengaturan ---------------- */
function pagePengaturan() {
  async function unggah(endpoint, inputId, imgId, kunci) {
    const f = $(inputId).files[0];
    if (!f) return toast("Pilih foto dulu", "gagal");
    const fd = new FormData();
    fd.append("foto", f);
    try {
      const r = await api(endpoint, { method: "POST", body: fd });
      $(imgId).src = r.foto;
      if (kunci) window.TOKO[kunci] = r.foto;
      toast("Foto disimpan");
    } catch (err) { toast(err.message, "gagal"); }
  }

  if (ADMIN) {
    async function muat() {
      try {
        const t = await api("/api/toko");
        $("#toko-nama").value = t.nama;
        $("#toko-alamat").value = t.alamat;
        $("#toko-telepon").value = t.telepon;
        $("#toko-footer").value = t.footer;
        $("#logo-toko").src = t.foto || "/static/img/toko/default.svg";
      } catch (err) { toast(err.message, "gagal"); }
    }
    $("#btn-simpan-toko").onclick = async () => {
      try {
        const body = {
          nama: $("#toko-nama").value, alamat: $("#toko-alamat").value,
          telepon: $("#toko-telepon").value, footer: $("#toko-footer").value,
        };
        await api("/api/toko", { method: "POST", body });
        window.TOKO = await api("/api/toko");
        $("#toko-nama").value = window.TOKO.nama;
        $("#toko-alamat").value = window.TOKO.alamat;
        $("#toko-telepon").value = window.TOKO.telepon;
        $("#toko-footer").value = window.TOKO.footer;
        toast("Pengaturan toko disimpan");
      } catch (err) { toast(err.message, "gagal"); }
    };
    $("#btn-simpan-foto-toko").onclick = () => unggah("/api/toko/foto", "#foto-toko", "#logo-toko", "foto");
    muat();
  } else {
    async function muat() {
      try {
        const p = await api("/api/profil");
        $("#foto-profil").src = p.foto || "/static/img/kasir/default.svg";
      } catch (err) { toast(err.message, "gagal"); }
    }
    $("#btn-simpan-foto-kasir").onclick = () => unggah("/api/profil/foto", "#foto-kasir", "#foto-profil");
    muat();
  }
}

/* ---------------- Shift kas (tombol di header) ---------------- */
async function bukaShiftModal() {
  try {
    const [daftar, profil] = await Promise.all([api("/api/shift"), api("/api/profil")]);
    const aktif = daftar.find(s => s.kasir_id === profil.id && s.tutup === null);
    if (aktif) {
      bukaModal(`
        <div class="p-6">
          <h3 class="text-lg font-extrabold text-slate-900">Shift aktif</h3>
          <p class="text-xs text-slate-500 mt-1">Mulai ${escapeHtml(aktif.buka)} · uang awal ${rupiah(aktif.awal)}</p>
          <p class="text-sm mt-3">Transaksi tunai selama shift: <b>${rupiah(aktif.tunai)}</b></p>
          <p class="text-sm">Seharusnya di laci: <b>${rupiah(aktif.awal + aktif.tunai)}</b></p>
          <form id="form-tutup-shift" class="mt-4 space-y-3">
            <div><label class="block text-xs font-bold text-slate-500 mb-1">Uang akhir (hitung fisik)</label>
              <input name="akhir" type="number" min="0" required class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400"></div>
            <div><label class="block text-xs font-bold text-slate-500 mb-1">Catatan</label>
              <input name="catatan" class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400"></div>
            <div class="flex justify-end gap-2 pt-2">
              <button type="button" data-tutup class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Batal</button>
              <button class="h-10 px-5 rounded-xl bg-indigo-600 text-white text-sm font-bold">Tutup shift</button>
            </div>
          </form>
        </div>`, "max-w-sm");
      $("#modal-root [data-tutup]").onclick = tutupModal;
      $("#form-tutup-shift").onsubmit = async e => {
        e.preventDefault();
        try {
          const r = await api("/api/shift/tutup", { method: "POST", body: Object.fromEntries(new FormData(e.target)) });
          tutupModal();
          toast(r.selisih === 0 ? "Shift ditutup, selisih 0" : `Shift ditutup, selisih ${rupiah(r.selisih)}`);
        } catch (err) { toast(err.message, "gagal"); }
      };
    } else {
      bukaModal(`
        <form id="form-buka-shift" class="p-6">
          <h3 class="text-lg font-extrabold text-slate-900 mb-4">Buka shift</h3>
          <p class="text-xs text-slate-500 mb-3">Masukkan uang awal di laci kasir.</p>
          <label class="block text-xs font-bold text-slate-500 mb-1">Uang awal (Rp)</label>
          <input name="awal" type="number" min="0" required class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400">
          <div class="flex justify-end gap-2 mt-6">
            <button type="button" data-tutup class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Batal</button>
            <button class="h-10 px-5 rounded-xl bg-indigo-600 text-white text-sm font-bold">Buka shift</button>
          </div>
        </form>`, "max-w-sm");
      $("#modal-root [data-tutup]").onclick = tutupModal;
      $("#form-buka-shift").onsubmit = async e => {
        e.preventDefault();
        try {
          await api("/api/shift/buka", { method: "POST", body: Object.fromEntries(new FormData(e.target)) });
          tutupModal(); toast("Shift dibuka");
        } catch (err) { toast(err.message, "gagal"); }
      };
    }
  } catch (err) { toast(err.message, "gagal"); }
}

/* ---------------- Bootstrap ---------------- */
document.addEventListener("DOMContentLoaded", () => {
  $("#tanggal-header").textContent = new Date().toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const diKasir = document.body.dataset.page === "kasir";
  if (diKasir) $("#sidebar").classList.add("nav-kasir-tutup");
  $("#btn-menu").onclick = () => $("#sidebar").classList.toggle(diKasir ? "nav-kasir-tutup" : "-translate-x-full");
  $("#btn-shift").onclick = bukaShiftModal;
  if ($("#btn-logout")) $("#btn-logout").onclick = async e => {
    e.preventDefault();
    try {
      const [shift, profil] = await Promise.all([api("/api/shift"), api("/api/profil")]);
      const aktif = shift.find(s => s.kasir_id === profil.id && s.tutup === null);
      if (!aktif) { location.href = "/logout"; return; }
      bukaModal(`
        <form id="form-logout-shift" class="p-6">
          <h3 class="text-lg font-extrabold text-slate-900">Tutup shift dulu</h3>
          <p class="text-sm text-slate-500 mt-1">Shift masih aktif sejak ${escapeHtml(aktif.buka)}. Isi uang akhir untuk keluar.</p>
          <p class="text-xs text-slate-400 mt-1">Transaksi tunai shift ini: ${rupiah(aktif.tunai)} · seharusnya ${rupiah(aktif.awal + aktif.tunai)}</p>
          <label class="block text-xs font-bold text-slate-500 mt-4 mb-1">Uang akhir (hitung fisik)</label>
          <input name="akhir" type="number" min="0" required class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400">
          <label class="block text-xs font-bold text-slate-500 mt-3 mb-1">Catatan</label>
          <input name="catatan" class="w-full h-10 px-3 rounded-xl border border-slate-200 outline-none focus:border-indigo-400">
          <div class="flex justify-end gap-2 mt-6">
            <button type="button" data-tutup class="h-10 px-4 rounded-xl border border-slate-200 text-sm font-semibold">Batal</button>
            <button class="h-10 px-5 rounded-xl bg-rose-600 text-white text-sm font-bold">Tutup &amp; keluar</button>
          </div>
        </form>`, "max-w-sm");
      $("#modal-root [data-tutup]").onclick = tutupModal;
      $("#form-logout-shift").onsubmit = async ev => {
        ev.preventDefault();
        try {
          await api("/api/shift/tutup", { method: "POST", body: Object.fromEntries(new FormData(ev.target)) });
          location.href = "/logout";
        } catch (err) { toast(err.message, "gagal"); }
      };
    } catch (err) { location.href = "/logout"; }
  };
  const halaman = { kasir: pageKasir, produk: pageProduk, riwayat: pageRiwayat, dashboard: pageDashboard, akun: pageAkun, pengaturan: pagePengaturan }[document.body.dataset.page];
  if (halaman) halaman();
});
