"""Pipeline ETL: Excel patient journey -> SQLite (star schema).

Jalankan:  python -m src.etl data/raw/patient_journey.xlsx
"""
import hashlib, hmac, os, sqlite3, sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DB_PATH", ROOT / "data" / "patient_journey.db"))
SALT = os.getenv("EPISODE_SALT", "ganti-salt-ini-di-secrets").encode()

TS_COLS = {
    "Waktu Appointment": "t_appointment", "Arrive": "t_arrive",
    "Seen By Nurse": "t_nurse", "Seen By Doc": "t_doc", "SOAP": "t_soap",
    "Order": "t_order", "Depart": "t_depart", "Review": "t_review",
    "Payment": "t_payment", "Checked": "t_checked", "Packed": "t_packed",
    "Collected": "t_collected",
}
DUR_COLS = {
    "Durasi Arrive - Seen By Nurse": "dur_arrive_nurse",
    "Durasi Arrive - Seen By Doc": "dur_arrive_doc",
    "Durasi Seen By Nurse - Seen By Doc": "dur_nurse_doc",
    "Durasi Seen By Doc - Departed": "dur_doc_depart",
    "Durasi SOAP - Order": "dur_soap_order",
    "Durasi Order - Review": "dur_order_review",
    "Durasi Review - Payment": "dur_review_payment",
    "Durasi Checked - Packed": "dur_checked_packed",
    "Durasi Payment - Packed": "dur_payment_packed",
    "Durasi Appointment - Arrive": "dur_appt_arrive",
    "Durasi Seen By Nurse - Payment": "dur_nurse_payment",
    "Durasi Total": "dur_total",
}
BINS = [-np.inf, 60, 90, 120, 240, np.inf]
LABELS = ["≤ 60 Menit", "61-90 Menit", "91-120 Menit", "121-240 Menit", "> 240 Menit"]
STAGE_TS = ["t_arrive", "t_nurse", "t_doc", "t_soap", "t_order", "t_depart",
            "t_review", "t_payment", "t_checked", "t_packed", "t_collected"]


# ---------------------------------------------------------------- EXTRACT
def extract(source) -> pd.DataFrame:
    df = pd.read_excel(source) if str(source).lower().endswith(("xlsx", "xls")) \
        else pd.read_csv(source)
    df.columns = [str(c).strip() for c in df.columns]
    return df


# -------------------------------------------------------------- TRANSFORM
def pseudonymize(x: str) -> str:
    return hmac.new(SALT, str(x).strip().encode(), hashlib.sha256).hexdigest()[:16]


def kategori_payor(nama: str) -> str:
    n = str(nama).lower()
    if "self" in n:
        return "Mandiri"
    if "rsps" in n:
        return "Internal RS"
    if any(k in n for k in ("asuransi", "admedika", "assurance")):
        return "Asuransi"
    if "pertamedika" in n:
        return "Korporasi"
    return "Lainnya"


def transform(raw: pd.DataFrame):
    df = raw.copy()
    n_in = len(df)
    df = df[df["Episode"].notna()]

    for src, dst in TS_COLS.items():
        df[dst] = pd.to_datetime(df.get(src), format="%d/%m/%Y %H:%M:%S", errors="coerce")
    for src, dst in DUR_COLS.items():
        df[dst] = pd.to_numeric(df.get(src), errors="coerce")

    df["episode_id"] = df["Episode"].map(pseudonymize)      # ETIKA: privasi
    n_dup = int(df.duplicated("episode_id", keep="last").sum())
    df = df.drop_duplicates("episode_id", keep="last")

    df["tanggal"] = df["t_arrive"].fillna(df["t_appointment"]).dt.strftime("%Y-%m-%d")
    df = df[df["tanggal"].notna()]
    df["nama_poli"] = df["Lokasi"].astype(str).str.replace(r"^PS\.", "", regex=True).str.strip()
    df["nama_payor"] = df["Payor"].astype(str).str.strip()
    df["racikan"] = (df["Racikan"].astype(str).str.upper() == "Y").astype(int)
    df["nps"] = pd.to_numeric(df.get("NPS"), errors="coerce")

    df["kategori_durasi"] = pd.cut(df["dur_total"], BINS, labels=LABELS).astype("object")
    df["bottleneck_opd"] = (df["dur_nurse_doc"] >= 60).astype(int)
    df["bottleneck_farmasi"] = (df["dur_checked_packed"] >= 60).astype(int)
    df["bottleneck_kasir"] = (df["dur_review_payment"] >= 60).astype(int)

    dur_cols = list(DUR_COLS.values())
    # dur_appt_arrive negatif = datang lebih awal (valid), jadi dikecualikan
    df["dq_negatif"] = (df[[c for c in dur_cols if c not in ("dur_total", "dur_appt_arrive")]] < 0).any(axis=1).astype(int)
    df["dq_tahap_kosong"] = df[STAGE_TS].isna().any(axis=1).astype(int)

    for c in list(TS_COLS.values()):
        df[c] = df[c].dt.strftime("%Y-%m-%d %H:%M:%S")
    stats = dict(baris_masuk=n_in, baris_valid=len(df), baris_duplikat=n_dup,
                 baris_dq_negatif=int(df["dq_negatif"].sum()))
    return df, stats


# ------------------------------------------------------------------- LOAD
FACT_COLS = (["episode_id", "tanggal", "racikan"] + list(TS_COLS.values())
             + list(DUR_COLS.values())
             + ["kategori_durasi", "bottleneck_opd", "bottleneck_farmasi",
                "bottleneck_kasir", "nps", "dq_negatif", "dq_tahap_kosong"])


def connect(path=DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
    return con


def load(df: pd.DataFrame, stats: dict, sumber: str, path=DB_PATH):
    con = connect(path)
    cur = con.cursor()
    for nama in df["nama_poli"].unique():
        cur.execute("INSERT OR IGNORE INTO dim_poli(nama_poli) VALUES (?)", (nama,))
    for nama in df["nama_payor"].unique():
        cur.execute("INSERT OR IGNORE INTO dim_payor(nama_payor,kategori_payor) VALUES (?,?)",
                    (nama, kategori_payor(nama)))
    poli = dict(cur.execute("SELECT nama_poli,poli_id FROM dim_poli").fetchall())
    payor = dict(cur.execute("SELECT nama_payor,payor_id FROM dim_payor").fetchall())

    out = df.copy()
    out["poli_id"] = out["nama_poli"].map(poli)
    out["payor_id"] = out["nama_payor"].map(payor)
    cols = FACT_COLS[:3] + ["poli_id", "payor_id"] + FACT_COLS[3:]
    out = out[cols].astype(object).where(out[cols].notna(), None)   # NaN -> NULL
    sql = f"INSERT OR REPLACE INTO fact_kunjungan({','.join(cols)}) VALUES ({','.join('?'*len(cols))})"
    cur.executemany(sql, out.values.tolist())      # idempoten: aman dijalankan ulang
    cur.execute("INSERT INTO etl_log(run_at,sumber,baris_masuk,baris_valid,baris_duplikat,"
                "baris_dq_negatif,status) VALUES (?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), str(sumber),
                 stats["baris_masuk"], stats["baris_valid"], stats["baris_duplikat"],
                 stats["baris_dq_negatif"], "SUKSES"))
    con.commit(); con.close()


def run(source, path=DB_PATH) -> dict:
    df, stats = transform(extract(source))
    load(df, stats, Path(str(source)).name, path)
    return stats


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "raw" / "patient_journey.xlsx"
    print(run(src))
