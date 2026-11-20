-- Skema bintang (star schema) untuk Patient Journey rawat jalan
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dim_poli (
    poli_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    nama_poli TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_payor (
    payor_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    nama_payor     TEXT NOT NULL UNIQUE,
    kategori_payor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_kunjungan (
    episode_id     TEXT PRIMARY KEY,          -- pseudonim (HMAC), bukan ID asli
    tanggal        TEXT NOT NULL,             -- YYYY-MM-DD
    poli_id        INTEGER NOT NULL REFERENCES dim_poli(poli_id),
    payor_id       INTEGER NOT NULL REFERENCES dim_payor(payor_id),
    racikan        INTEGER NOT NULL DEFAULT 0,
    -- timestamp tiap tahap layanan
    t_appointment TEXT, t_arrive TEXT, t_nurse TEXT, t_doc TEXT, t_soap TEXT,
    t_order TEXT, t_depart TEXT, t_review TEXT, t_payment TEXT,
    t_checked TEXT, t_packed TEXT, t_collected TEXT,
    -- durasi (menit)
    dur_arrive_nurse REAL, dur_arrive_doc REAL, dur_nurse_doc REAL,
    dur_doc_depart REAL, dur_soap_order REAL, dur_order_review REAL,
    dur_review_payment REAL, dur_checked_packed REAL, dur_payment_packed REAL,
    dur_appt_arrive REAL, dur_nurse_payment REAL, dur_total REAL,
    kategori_durasi TEXT,
    bottleneck_opd     INTEGER NOT NULL DEFAULT 0,
    bottleneck_farmasi INTEGER NOT NULL DEFAULT 0,
    bottleneck_kasir   INTEGER NOT NULL DEFAULT 0,
    nps REAL,
    dq_negatif INTEGER NOT NULL DEFAULT 0,    -- ada durasi negatif (anomali urutan waktu)
    dq_tahap_kosong INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_fact_tanggal ON fact_kunjungan(tanggal);
CREATE INDEX IF NOT EXISTS ix_fact_poli    ON fact_kunjungan(poli_id);
CREATE INDEX IF NOT EXISTS ix_fact_payor   ON fact_kunjungan(payor_id);

CREATE TABLE IF NOT EXISTS etl_log (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at      TEXT NOT NULL,
    sumber      TEXT NOT NULL,
    baris_masuk INTEGER, baris_valid INTEGER, baris_duplikat INTEGER,
    baris_dq_negatif INTEGER, status TEXT
);

CREATE VIEW IF NOT EXISTS vw_kunjungan AS
SELECT f.*, p.nama_poli, y.nama_payor, y.kategori_payor
FROM fact_kunjungan f
JOIN dim_poli  p ON p.poli_id  = f.poli_id
JOIN dim_payor y ON y.payor_id = f.payor_id;
