
import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.storage import local


def run_async(coro):
    return asyncio.run(coro)


def make_upload(
    filename: str,
    content_type: str,
    content: bytes,
) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    test_upload_dir = tmp_path / "uploads" / "submissions"
    monkeypatch.setattr(local, "UPLOAD_DIR", test_upload_dir)
    return test_upload_dir


@pytest.mark.parametrize(
    ("filename", "mime_type", "content"),
    [
        ("assignment.pdf", "application/pdf", b"%PDF-1.7 test PDF"),
        ("assignment.png", "image/png", b"\x89PNG\r\n\x1a\n test PNG"),
        ("assignment.jpg", "image/jpeg", b"\xff\xd8\xff test JPEG"),
        ("assignment.jpeg", "image/jpeg", b"\xff\xd8\xff test JPEG"),
        ("assignment.webp", "image/webp", b"RIFF\x04\x00\x00\x00WEBPtest"),
        ("assignment.txt", "text/plain", b"Hello, this is a submission."),
    ],
)
def test_valid_uploads_are_stored_and_can_be_deleted(
    upload_dir,
    filename,
    mime_type,
    content,
):
    upload = make_upload(filename, mime_type, content)

    stored = run_async(local.save_submission_file(upload))

    destination = upload_dir.parent / stored.storage_key

    assert destination.is_file()
    assert destination.read_bytes() == content
    assert stored.file_name == filename
    assert stored.mime_type == mime_type
    assert stored.file_size_bytes == len(content)

    local.delete_submission_file(stored.storage_key)

    assert not destination.exists()


def test_unsupported_extension_is_rejected(upload_dir):
    upload = make_upload(
        "assignment.exe",
        "application/octet-stream",
        b"some content",
    )

    with pytest.raises(ValueError, match="Unsupported file extension"):
        run_async(local.save_submission_file(upload))


def test_mismatched_mime_type_is_rejected(upload_dir):
    upload = make_upload(
        "assignment.pdf",
        "image/png",
        b"%PDF-1.7 test PDF",
    )

    with pytest.raises(ValueError, match="content type"):
        run_async(local.save_submission_file(upload))


@pytest.mark.parametrize(
    ("filename", "mime_type", "content"),
    [
        ("assignment.pdf", "application/pdf", b"not a PDF"),
        ("assignment.png", "image/png", b"not a PNG"),
        ("assignment.jpg", "image/jpeg", b"not a JPEG"),
        ("assignment.webp", "image/webp", b"not a WEBP"),
    ],
)
def test_invalid_file_signatures_are_rejected(
    upload_dir,
    filename,
    mime_type,
    content,
):
    upload = make_upload(filename, mime_type, content)

    with pytest.raises(ValueError, match="does not match"):
        run_async(local.save_submission_file(upload))
    assert not list(upload_dir.rglob("*"))


def test_empty_file_is_rejected(upload_dir):
    upload = make_upload(
        "empty.txt",
        "text/plain",
        b"",
    )

    with pytest.raises(ValueError, match="empty"):
        run_async(local.save_submission_file(upload))

    assert not upload_dir.exists()


def test_file_larger_than_limit_is_rejected(upload_dir):
    content = b"A" * (local.MAX_FILE_SIZE_BYTES + 1)

    upload = make_upload(
        "large.txt",
        "text/plain",
        content,
    )

    with pytest.raises(ValueError, match="10 MB"):
        run_async(local.save_submission_file(upload))

    assert not upload_dir.exists()


@pytest.mark.parametrize(
    "content",
    [
        b"\xff\xfe\xfa",
        b"valid text\x00binary",
    ],
)
def test_binary_content_disguised_as_txt_is_rejected(
    upload_dir,
    content,
):
    upload = make_upload(
        "assignment.txt",
        "text/plain",
        content,
    )

    with pytest.raises(ValueError, match="does not match"):
        run_async(local.save_submission_file(upload))

    assert not upload_dir.exists()


def test_partial_write_failure_cleans_up_files(
    upload_dir,
    monkeypatch,
):
    original_open = Path.open

    class PartialFailureWriter:
        def __init__(self, file_handle):
            self.file_handle = file_handle

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.file_handle.close()
            return False

        def write(self, content):
            self.file_handle.write(content[:3])
            self.file_handle.flush()
            raise OSError("Simulated disk write failure")

    def failing_open(path, mode="r", *args, **kwargs):
        file_handle = original_open(path, mode, *args, **kwargs)

        if path.suffix == ".tmp" and mode == "xb":
            return PartialFailureWriter(file_handle)

        return file_handle

    monkeypatch.setattr(Path, "open", failing_open)

    upload = make_upload(
        "assignment.txt",
        "text/plain",
        b"Valid submission text",
    )

    with pytest.raises(ValueError, match="Unable to store"):
        run_async(local.save_submission_file(upload))

    assert upload_dir.exists() and not list(upload_dir.rglob("*"))


def test_path_traversal_storage_key_is_rejected(upload_dir):
    with pytest.raises(ValueError, match="Invalid storage key"):
        local.delete_submission_file("../../outside.txt")


def test_deleting_missing_file_is_safe(upload_dir):
    local.delete_submission_file(
        "submissions/nonexistent/nonexistent.txt"
    )
