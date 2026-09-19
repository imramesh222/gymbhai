"""The S3 backend, against a fake client: the same calls R2 would get."""

import pytest

from app.core.config import settings
from app.services import storage


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}

    def put_object(self, Bucket, Key, Body, ContentType):
        self.objects[(Bucket, Key)] = (Body, ContentType)

    def get_object(self, Bucket, Key):
        from botocore.exceptions import ClientError

        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")

        class Body:
            def read(inner) -> bytes:
                return self.objects[(Bucket, Key)][0]

        return {"Body": Body()}

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


@pytest.fixture
def s3(monkeypatch) -> FakeS3:
    fake = FakeS3()
    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket", "gymbhai-files")
    monkeypatch.setattr(storage, "_s3", lambda: fake)
    return fake


def test_put_read_delete(s3: FakeS3) -> None:
    key = storage.put("gyms/x/members/a.jpg", b"\\xff\\xd8\\xff")
    assert s3.objects[("gymbhai-files", key)][1] == "image/jpeg"
    assert storage.read(key) == b"\\xff\\xd8\\xff"
    storage.delete(key)
    assert storage.read(key) is None


def test_s3_needs_its_settings() -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="S3_BUCKET"):
        Settings(storage_backend="s3", _env_file=None)
