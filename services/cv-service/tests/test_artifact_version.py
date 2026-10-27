import pytest

from app.runtime import ModelSettings


def test_version_tag_resolves_approved_version_without_changing_artifact_path() -> None:
    from app.runtime import resolve_model_version

    class Blob:
        def download_as_text(self) -> str:
            return "cv-vit-b16-v4\n"

    class Bucket:
        def __init__(self) -> None:
            self.requested_blob = None

        def blob(self, name: str) -> Blob:
            self.requested_blob = name
            return Blob()

    class StorageClient:
        def __init__(self) -> None:
            self.bucket_instance = Bucket()

        def bucket(self, name: str) -> Bucket:
            return self.bucket_instance

    settings = ModelSettings(
        model_object="models/cv/approved/vit_b16.pth",
        model_version_tag_object="models/cv/approved/VERSION",
    )
    client = StorageClient()

    version = resolve_model_version(
        settings, storage_client_factory=lambda **_: client
    )

    assert version == "cv-vit-b16-v4"
    assert client.bucket_instance.requested_blob == "models/cv/approved/VERSION"
    assert settings.model_object == "models/cv/approved/vit_b16.pth"


def test_load_runtime_rejects_a_malformed_approved_version_tag() -> None:
    from app.runtime import load_runtime

    class Blob:
        def download_as_text(self) -> str:
            return "not an approved version\nsecond line"

    class Bucket:
        def blob(self, name: str) -> Blob:
            return Blob()

    class StorageClient:
        def bucket(self, name: str) -> Bucket:
            return Bucket()

    with pytest.raises(RuntimeError, match="approved model version tag is malformed"):
        load_runtime(
            ModelSettings(model_version_tag_object="models/cv/approved/VERSION"),
            storage_client_factory=lambda **_: StorageClient(),
        )
