# Dashboard Analisis Patient Journey Rawat Jalan
Proyek Basis Data (CPL: arsitektur DB, deployment AI/software, etika) + Deployment Aplikasi (SD221235, Sub-CPMK 3-4).

## Jalankan lokal
    pip install -r requirements.txt
    python -m src.etl data/raw/patient_journey.xlsx   # ETL -> data/patient_journey.db
    streamlit run app.py
## Deploy
- Streamlit Community Cloud: push repo ke GitHub, pilih app.py, isi Secrets: `ADMIN_PASSWORD`, `EPISODE_SALT`.
- Docker: `docker build -t pj . && docker run -p 8501:8501 -e EPISODE_SALT=xxx pj`
## Data asli (ribuan baris)
Ganti `data/raw/patient_journey.xlsx` lalu jalankan ETL. Jika perlu skala lebih besar, pindahkan DB ke PostgreSQL
(skema di sql/schema.sql hampir kompatibel; ganti AUTOINCREMENT -> SERIAL dan sqlite3 -> SQLAlchemy).
