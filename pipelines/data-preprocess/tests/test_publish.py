from __future__ import annotations

from pathlib import Path

from mirror_data_preprocess.publish import publish_directory


class FakeBlob:
    def __init__(self, name: str) -> None:
        self.name = name
        self.uploaded: bytes | None = None

    def upload_from_filename(self, filename: str) -> None:
        self.uploaded = Path(filename).read_bytes()


class FakeBucket:
    def __init__(self) -> None:
        self.blobs: list[FakeBlob] = []

    def blob(self, name: str) -> FakeBlob:
        blob = FakeBlob(name)
        self.blobs.append(blob)
        return blob


class FakeClient:
    def __init__(self) -> None:
        self.bucket_name: str | None = None
        self.bucket_instance = FakeBucket()

    def bucket(self, name: str) -> FakeBucket:
        self.bucket_name = name
        return self.bucket_instance


class FailingBlob(FakeBlob):
    def upload_from_filename(self, filename: str) -> None:
        raise RuntimeError("simulated GCS failure")


class FailingBucket(FakeBucket):
    def blob(self, name: str) -> FakeBlob:
        blob: FakeBlob = FailingBlob(name) if name.endswith("bad.csv") else FakeBlob(name)
        self.blobs.append(blob)
        return blob


class FailingClient(FakeClient):
    def __init__(self) -> None:
        self.bucket_name: str | None = None
        self.bucket_instance = FailingBucket()


def test_publish_directory_preserves_relative_paths_under_gcs_prefix(tmp_path: Path) -> None:
    output = tmp_path / "output"
    nested = output / "manifests" / "train.csv"
    nested.parent.mkdir(parents=True)
    nested.write_text("path,label,split\n", encoding="utf-8")
    (output / "metadata.json").write_text("{}\n", encoding="utf-8")
    client = FakeClient()

    uploaded = publish_directory(
        output, "gs://bucket-a/data/processed/fer2013/v1/", client, max_workers=2
    )

    assert client.bucket_name == "bucket-a"
    assert uploaded == 2
    assert [blob.name for blob in client.bucket_instance.blobs] == [
        "data/processed/fer2013/v1/manifests/train.csv",
        "data/processed/fer2013/v1/metadata.json",
    ]


def test_publish_directory_rejects_invalid_worker_count_and_stops_on_upload_error(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "bad.csv").write_text("bad\n", encoding="utf-8")
    (output / "later.csv").write_text("later\n", encoding="utf-8")

    try:
        publish_directory(output, "gs://bucket-a/prefix", FakeClient(), max_workers=0)
    except ValueError as exc:
        assert "max_workers" in str(exc)
    else:
        raise AssertionError("expected invalid worker count to be rejected")

    try:
        publish_directory(output, "gs://bucket-a/prefix", FailingClient(), max_workers=1)
    except RuntimeError as exc:
        assert "simulated GCS failure" in str(exc)
    else:
        raise AssertionError("expected the GCS upload failure to propagate")
