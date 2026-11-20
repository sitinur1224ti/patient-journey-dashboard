"""Dashboard Streamlit: Analisis Patient Journey Rawat Jalan.
Jalankan:  streamlit run app.py
"""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from src import db, etl

st.set_page_config(page_title="Patient Journey Rawat Jalan", page_icon="🏥", layout="wide")


# ------------------------------------------------------------ inisialisasi
@st.cache_resource
def init_db():
    """Bangun DB dari data contoh bila belum ada (penting untuk deploy pertama kali)."""
    if not Path(etl.DB_PATH).exists():
        etl.run(etl.run(etl.ROOT / "data" / "sample" / "patient_journey_contoh.xlsx"))
    return True


init_db()


@st.cache_data(ttl=600, show_spinner=False)
def cached(fn_name: str, f: tuple):
    flt = dict(f)
    return getattr(db, fn_name)(flt)


def F(flt):  # dict -> tuple hashable untuk cache
    return tuple((k, tuple(v) if isinstance(v, list) else v) for k, v in flt.items())


# ------------------------------------------------------------------ sidebar
st.sidebar.title("🏥 Patient Journey")
halaman = st.sidebar.radio("Navigasi", [
    "1. Ringkasan Eksekutif", "2. Alur Layanan & Bottleneck", "3. Poli & Payor",
    "4. Kualitas Data & Pipeline ETL", "5. Etika & Privasi"])

mn, mx, poli_opt, payor_opt = db.options()
st.sidebar.subheader("Filter")
rentang = st.sidebar.date_input("Periode", (pd.to_datetime(mn), pd.to_datetime(mx)))
if len(rentang) != 2:
    st.info("Pilih tanggal awal dan akhir."); st.stop()
poli = st.sidebar.multiselect("Poli", poli_opt)
payor = st.sidebar.multiselect("Kategori Payor", payor_opt)
excl = st.sidebar.checkbox("Kecualikan data anomali (durasi negatif)", value=False)
flt = dict(start=str(rentang[0]), end=str(rentang[1]), poli=poli, payor=payor, exclude_dq=excl)
key = F(flt)

with st.sidebar.expander("🔒 Muat data baru (admin)"):
    pw = st.text_input("Password", type="password")
    up = st.file_uploader("Excel/CSV patient journey", type=["xlsx", "xls", "csv"])
    if st.button("Jalankan ETL") and up is not None:
        if pw != st.secrets.get("ADMIN_PASSWORD", None):
            st.error("Password salah / belum diatur di secrets.")
        else:
            with tempfile.NamedTemporaryFile(suffix=Path(up.name).suffix, delete=False) as t:
                t.write(up.getvalue())
            st.success(f"ETL selesai: {etl.run(t.name)}")
            st.cache_data.clear(); st.rerun()

st.title("Dashboard Analisis Patient Journey Rawat Jalan")
st.caption("Pemantauan waktu tunggu & bottleneck layanan: poli → perawat → dokter → kasir → farmasi")

# ----------------------------------------------------------------- halaman 1
if halaman.startswith("1"):
    k = cached("kpi", key)
    if int(k["kunjungan"]) == 0:
        st.warning("Tidak ada data untuk filter ini."); st.stop()
    c = st.columns(5)
    c[0].metric("Total Kunjungan", f"{int(k['kunjungan']):,}")
    c[1].metric("Rata-rata Durasi Total", f"{k['rata_total']} mnt")
    c[2].metric("Selesai ≤ 60 mnt", f"{k['pct_le60']}%")
    c[3].metric("Farmasi ≥ 60 mnt", f"{k['pct_farmasi']}%")
    c[4].metric("Kasir ≥ 60 mnt", f"{k['pct_kasir']}%")
    if pd.isna(k["nps"]):
        st.caption("NPS belum terisi pada data ini.")
    else:
        st.metric("Rata-rata NPS", k["nps"])

    a, b = st.columns(2)
    with a:
        st.subheader("Tren kunjungan harian")
        t = cached("tren_harian", key).set_index("tanggal")
        st.line_chart(t["kunjungan"])
    with b:
        st.subheader("Distribusi durasi total")
        d = cached("distribusi", key).set_index("kategori_durasi").reindex(etl.LABELS).fillna(0)
        st.bar_chart(d["n"])

# ----------------------------------------------------------------- halaman 2
elif halaman.startswith("2"):
    st.subheader("Durasi per tahap layanan (menit)")
    t = cached("tahap", key)
    st.bar_chart(t.set_index("tahap")["median_menit"])
    st.caption("Median dipakai karena tahan terhadap outlier (mis. pembayaran berhari-hari setelah review).")
    st.dataframe(t, hide_index=True)
    if not t.empty:
        s = t.sort_values("median_menit", ascending=False).iloc[0]
        st.info(f"Tahap paling lama (median): **{s['tahap']}** — {s['median_menit']} menit.")
    st.subheader("Kasus terlama")
    st.dataframe(cached("detail", key), hide_index=True)

# ----------------------------------------------------------------- halaman 3
elif halaman.startswith("3"):
    a, b = st.columns(2)
    with a:
        st.subheader("Rata-rata durasi total per poli")
        p = cached("per_poli", key)
        st.bar_chart(p.set_index("nama_poli")["rata_total"])
        st.dataframe(p, hide_index=True)
    with b:
        st.subheader("Per kategori payor")
        y = cached("per_payor", key)
        st.bar_chart(y.set_index("kategori_payor")["rata_total"])
        st.dataframe(y, hide_index=True)

# ----------------------------------------------------------------- halaman 4
elif halaman.startswith("4"):
    dq = db.kualitas_data()
    c = st.columns(4)
    c[0].metric("Total baris di DB", int(dq["total"]))
    c[1].metric("Durasi negatif", int(dq["negatif"]))
    c[2].metric("Tahap kosong", int(dq["tahap_kosong"]))
    c[3].metric("NPS kosong", int(dq["nps_kosong"]))
    st.subheader("Riwayat eksekusi ETL")
    st.dataframe(db.etl_log(), hide_index=True)
    st.subheader("Alur pipeline")
    st.code("Excel/CSV → Extract → Transform (parse waktu, pseudonim ID, flag bottleneck, "
            "flag anomali) → Load (SQLite: dim_poli, dim_payor, fact_kunjungan) → "
            "Query SQL → Dashboard Streamlit", language="text")
    st.subheader("Skema basis data")
    st.code((etl.ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"), language="sql")

# ----------------------------------------------------------------- halaman 5
else:
    st.subheader("Etika data & privasi")
    st.markdown("""
- **Pseudonimisasi:** nomor episode diubah menjadi HMAC-SHA256 bersalt sebelum disimpan; ID asli tidak masuk database.
- **Minimisasi data:** hanya atribut proses layanan yang disimpan; tidak ada nama, NIK, atau diagnosis.
- **Akses terkontrol:** fitur muat data hanya untuk admin (password di `st.secrets`).
- **Integritas data:** durasi negatif & tahap kosong ditandai, bukan dihapus diam-diam; ETL idempoten.
- **Penggunaan wajar:** dashboard untuk perbaikan proses layanan, bukan menilai individu tenaga kesehatan.
""")
