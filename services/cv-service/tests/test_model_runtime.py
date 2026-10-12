from pathlib import Path

import pytest
import torch


def test_load_model_downloads_configured_checkpoint_to_cpu(tmp_path: Path) -> None:
    from app.runtime import ModelSettings, load_model

    class Blob:
        name = "models/cv/inherited-v3/vit_b16_v3_best.pth"

        def download_to_filename(self, filename: str) -> None:
            torch.save({"state_dict": {"weight": torch.tensor([1.0])}}, filename)

    class Bucket:
        def __init__(self) -> None:
            self.requested_blob = None

        def blob(self, name: str) -> Blob:
            self.requested_blob = name
            return Blob()

    class StorageClient:
        def __init__(self) -> None:
            self.requested_bucket = None
            self.bucket_instance = Bucket()

        def bucket(self, name: str) -> Bucket:
            self.requested_bucket = name
            return self.bucket_instance

    class Model(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.weight = torch.nn.Parameter(torch.tensor([0.0]))

    storage_client = StorageClient()
    settings = ModelSettings(model_cache_dir=tmp_path)

    model = load_model(
        settings,
        storage_client_factory=lambda **_: storage_client,
        model_factory=Model,
    )

    assert storage_client.requested_bucket == "mirror-ac215-data"
    assert storage_client.bucket_instance.requested_blob == (
        "models/cv/inherited-v3/vit_b16_v3_best.pth"
    )
    assert model.weight.detach().tolist() == [1.0]
    assert model.training is False
    assert next(model.parameters()).device.type == "cpu"


def test_load_model_selects_the_mirror_cloud_project(tmp_path: Path) -> None:
    from app.runtime import ModelSettings, load_model

    class Blob:
        def download_to_filename(self, filename: str) -> None:
            torch.save({"state_dict": {"weight": torch.tensor([1.0])}}, filename)

    class Bucket:
        def blob(self, name: str) -> Blob:
            return Blob()

    class Client:
        def bucket(self, name: str) -> Bucket:
            return Bucket()

    requested: dict[str, str] = {}

    def storage_factory(*, project: str) -> Client:
        requested["project"] = project
        return Client()

    class Model(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.weight = torch.nn.Parameter(torch.tensor([0.0]))

    load_model(
        ModelSettings(model_cache_dir=tmp_path),
        storage_client_factory=storage_factory,
        model_factory=Model,
    )

    assert requested["project"] == "mirror-ac215"


def test_load_model_rejects_checkpoint_with_wrong_class_count(tmp_path: Path) -> None:
    from app.runtime import ModelSettings, load_model

    class Blob:
        def download_to_filename(self, filename: str) -> None:
            torch.save({"state_dict": {"weight": torch.zeros(6)}}, filename)

    class StorageClient:
        def bucket(self, name: str) -> object:
            return type("Bucket", (), {"blob": lambda self, name: Blob()})()

    class Model(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.weight = torch.nn.Parameter(torch.zeros(7))

    with pytest.raises(RuntimeError, match="checkpoint"):
        load_model(
            ModelSettings(model_cache_dir=tmp_path),
            storage_client_factory=lambda **_: StorageClient(),
            model_factory=Model,
        )


def test_cpu_face_detector_loads_its_embedded_cascade() -> None:
    from app.runtime import FaceDetector

    detector = FaceDetector()

    assert detector is not None


def test_vit_factory_matches_the_inherited_checkpoint_classifier_keys() -> None:
    from app.runtime import _vit_b16_factory

    state = _vit_b16_factory().state_dict()

    assert "heads.head.1.weight" in state
    assert tuple(state["heads.head.1.weight"].shape) == (7, 768)
