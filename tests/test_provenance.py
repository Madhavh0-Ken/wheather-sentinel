from datetime import datetime, timezone

from storm_nowcast.data.provenance import read_manifest, sha256_file, write_manifest
from storm_nowcast.models.schemas import ProvenanceRecord


def test_checksum_and_manifest_preserve_exact_source_metadata(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"official-observation")
    record = ProvenanceRecord(
        provider="NOAA Climate Prediction Center",
        product="CMORPH V0.x RAW 8km-30min",
        source_url="https://ftp.cpc.ncep.noaa.gov/official.bz2",
        acquired_at=datetime(2023, 7, 10, tzinfo=timezone.utc),
        observation_start=datetime(2023, 7, 9, tzinfo=timezone.utc),
        observation_end=datetime(2023, 7, 9, 0, 30, tzinfo=timezone.utc),
        sha256=sha256_file(source),
        processing_steps=["decompressed bzip2", "subset regional grid"],
        local_file=str(source),
    )

    manifest = tmp_path / "manifest.json"
    write_manifest(manifest, [record])

    body = manifest.read_text(encoding="utf-8")
    assert '"provider": "NOAA Climate Prediction Center"' in body
    assert record.sha256 == "ea3cd48cbecf05dd3fd2c30f37617e350bc285be4f4bdce9ebcad1f46530c66a"
    assert '"is_synthetic": false' in body
    assert read_manifest(manifest) == [record]
