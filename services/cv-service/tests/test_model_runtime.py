from pathlib import Path

import pytest
import torch


def test_load_model_downloads_configured_checkpoint_to_cpu(tmp_path: Path) -> None:
    from app.runtime import ModelSettings, load_model

    class Blob:
        name = "models/cv/v4/vit_b16_v4.pth"

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
    assert storage_client.bucket_instance.requested_blob == ("models/cv/v4/vit_b16_v4.pth")
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


def test_face_detector_creates_yunet_with_the_file_and_threshold(stub_yunet) -> None:
    from app.runtime import FACE_SCORE_THRESHOLD, FaceDetector

    FaceDetector(model_path=stub_yunet.path)
    path, config, size, threshold, nms, top_k = stub_yunet.detector.created_with
    assert (path, config, size) == (str(stub_yunet.path), "", (320, 320))
    assert (threshold, nms, top_k) == (FACE_SCORE_THRESHOLD, 0.3, 5000)


def test_face_detector_returns_none_when_yunet_finds_nothing(stub_yunet) -> None:
    import numpy as np

    from app.runtime import FaceDetector

    detector = FaceDetector(model_path=stub_yunet.path)
    assert detector(np.full((240, 320, 3), 128, dtype=np.uint8)) is None


def test_face_detector_refuses_a_model_file_with_another_hash(tmp_path) -> None:
    from app.runtime import FaceDetector

    fake = tmp_path / "yunet.onnx"
    fake.write_bytes(b"not the model")
    with pytest.raises(RuntimeError, match="sha256"):
        FaceDetector(model_path=fake)


def test_face_detector_refuses_a_missing_model_file(tmp_path) -> None:
    from app.runtime import FaceDetector

    with pytest.raises(RuntimeError, match="not found"):
        FaceDetector(model_path=tmp_path / "missing.onnx")


def test_square_face_crop_is_square_and_centred_on_the_box() -> None:
    import numpy as np

    from app.runtime import square_face_crop

    image = np.zeros((240, 320, 3), dtype=np.uint8)
    crop = square_face_crop(image, (100.0, 50.0, 60.0, 80.0))  # taller than wide

    assert crop.shape[:2] == (80, 80)


def test_square_face_crop_is_clipped_at_the_image_edge() -> None:
    import numpy as np

    from app.runtime import square_face_crop

    image = np.zeros((240, 320, 3), dtype=np.uint8)
    crop = square_face_crop(image, (-10.0, 200.0, 60.0, 60.0))

    assert crop.shape[:2] == (40, 50)


def test_vit_factory_matches_the_inherited_checkpoint_classifier_keys() -> None:
    from app.runtime import _vit_b16_factory

    state = _vit_b16_factory().state_dict()

    assert "heads.head.1.weight" in state
    assert tuple(state["heads.head.1.weight"].shape) == (7, 768)
