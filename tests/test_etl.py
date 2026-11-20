from src import etl, db

def test_pipeline(tmp_path):
    path = tmp_path / "t.db"
    s = etl.run(etl.ROOT / "data/raw/patient_journey.xlsx", path)
    assert s["baris_valid"] == s["baris_masuk"] - s["baris_duplikat"]
    etl.run(etl.ROOT / "data/raw/patient_journey.xlsx", path)   # idempoten
    assert db.q("SELECT COUNT(*) n FROM fact_kunjungan", path=path).n[0] == s["baris_valid"]
    assert not db.q("SELECT 1 FROM fact_kunjungan WHERE episode_id LIKE 'OS%'", path=path).shape[0]
