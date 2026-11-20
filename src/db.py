"""Lapisan akses data: semua agregasi berat dijalankan di SQL, bukan di pandas."""
import sqlite3
import pandas as pd
from .etl import DB_PATH, connect


def _where(f: dict):
    cl, p = ["tanggal BETWEEN ? AND ?"], [f["start"], f["end"]]
    for key, col in (("poli", "nama_poli"), ("payor", "kategori_payor")):
        if f.get(key):
            cl.append(f"{col} IN ({','.join('?'*len(f[key]))})"); p += list(f[key])
    if f.get("exclude_dq"):
        cl.append("dq_negatif = 0")
    return " AND ".join(cl), p


def q(sql, params=(), path=DB_PATH) -> pd.DataFrame:
    con = connect(path)
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


def options(path=DB_PATH):
    d = q("SELECT MIN(tanggal) mn, MAX(tanggal) mx FROM fact_kunjungan", path=path)
    poli = q("SELECT nama_poli FROM dim_poli ORDER BY 1", path=path)["nama_poli"].tolist()
    pay = q("SELECT DISTINCT kategori_payor FROM dim_payor ORDER BY 1", path=path)["kategori_payor"].tolist()
    return d.loc[0, "mn"], d.loc[0, "mx"], poli, pay


def kpi(f, path=DB_PATH):
    w, p = _where(f)
    return q(f"""SELECT COUNT(*) kunjungan,
        ROUND(AVG(dur_total),1) rata_total, ROUND(AVG(dur_arrive_nurse),1) rata_tunggu_perawat,
        ROUND(100.0*SUM(dur_total<=60)/NULLIF(COUNT(dur_total),0),1) pct_le60,
        ROUND(100.0*SUM(bottleneck_farmasi)/NULLIF(COUNT(*),0),1) pct_farmasi,
        ROUND(100.0*SUM(bottleneck_kasir)/NULLIF(COUNT(*),0),1) pct_kasir,
        ROUND(AVG(nps),1) nps
        FROM vw_kunjungan WHERE {w}""", p, path).iloc[0]


def tren_harian(f, path=DB_PATH):
    w, p = _where(f)
    return q(f"""SELECT tanggal, COUNT(*) kunjungan, ROUND(AVG(dur_total),1) rata_total
                 FROM vw_kunjungan WHERE {w} GROUP BY tanggal ORDER BY tanggal""", p, path)


def per_poli(f, path=DB_PATH):
    w, p = _where(f)
    return q(f"""SELECT nama_poli, COUNT(*) kunjungan, ROUND(AVG(dur_total),1) rata_total,
                 ROUND(AVG(dur_nurse_doc),1) rata_nurse_doc,
                 ROUND(100.0*SUM(dur_total>120)/NULLIF(COUNT(dur_total),0),1) pct_gt120
                 FROM vw_kunjungan WHERE {w} GROUP BY nama_poli ORDER BY rata_total DESC""", p, path)


def per_payor(f, path=DB_PATH):
    w, p = _where(f)
    return q(f"""SELECT kategori_payor, COUNT(*) kunjungan, ROUND(AVG(dur_total),1) rata_total,
                 ROUND(AVG(dur_review_payment),1) rata_review_payment
                 FROM vw_kunjungan WHERE {w} GROUP BY kategori_payor ORDER BY kunjungan DESC""", p, path)


def distribusi(f, path=DB_PATH):
    w, p = _where(f)
    return q(f"""SELECT kategori_durasi, COUNT(*) n FROM vw_kunjungan
                 WHERE {w} AND kategori_durasi IS NOT NULL GROUP BY kategori_durasi""", p, path)


def tahap(f, path=DB_PATH):
    """Median & rata-rata durasi per tahap (median tahan outlier) -> cari bottleneck."""
    w, p = _where(f)
    cols = {"Tunggu perawat": "dur_arrive_nurse", "Perawat → Dokter": "dur_nurse_doc",
            "Dokter → Pulang": "dur_doc_depart", "SOAP → Order": "dur_soap_order",
            "Order → Review": "dur_order_review", "Review → Payment (Kasir)": "dur_review_payment",
            "Checked → Packed (Farmasi)": "dur_checked_packed"}
    d = q(f"SELECT {','.join(cols.values())} FROM vw_kunjungan WHERE {w}", p, path)
    d = d.where(d >= 0)                      # durasi negatif = anomali, diabaikan
    d.columns = list(cols.keys())
    return pd.DataFrame({"tahap": d.columns, "median_menit": d.median().round(1).values,
                         "rata_menit": d.mean().round(1).values}).dropna()


def kualitas_data(path=DB_PATH):
    return q("""SELECT COUNT(*) total, SUM(dq_negatif) negatif, SUM(dq_tahap_kosong) tahap_kosong,
                SUM(nps IS NULL) nps_kosong FROM fact_kunjungan""", path=path).iloc[0]


def etl_log(path=DB_PATH):
    return q("SELECT * FROM etl_log ORDER BY run_id DESC LIMIT 20", path=path)


def detail(f, limit=1000, path=DB_PATH):
    w, p = _where(f)
    return q(f"""SELECT episode_id, tanggal, nama_poli, kategori_payor, dur_total,
                 kategori_durasi, bottleneck_opd, bottleneck_farmasi, bottleneck_kasir
                 FROM vw_kunjungan WHERE {w} ORDER BY dur_total DESC LIMIT {int(limit)}""", p, path)
