
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BACKEND_DIR / "uploads" / "submissions"

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_TYPES = {
    ".pdf": {"application/pdf"},
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".webp": {"image/webp"},
    ".txt": {"text/plain"},
}


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    file_name: str
    mime_type: str
    file_size_bytes: int


def _validate_file_signature(extension: str, content: bytes) -> bool:
    signatures = {
        ".pdf": content.startswith(b"%PDF-"),
        ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": content.startswith(b"\xff\xd8\xff"),
        ".jpeg": content.startswith(b"\xff\xd8\xff"),
        ".webp": (
            len(content) >= 12
            and content[:4] == b"RIFF"
            and content[8:12] == b"WEBP"
        ),
        ".txt": _is_valid_text(content),
    }

    return signatures.get(extension, False)


def _is_valid_text(content: bytes) -> bool:
    if b"\x00" in content:
        return False

    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False

    return True


async def save_submission_file(upload: UploadFile) -> StoredFile:
    original_name = Path(upload.filename or "").name
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_TYPES:
        raise ValueError("Unsupported file extension.")

    mime_type = (upload.content_type or "").lower()

    if mime_type not in ALLOWED_TYPES[extension]:
        raise ValueError("Unsupported or mismatched file content type.")

    content = await upload.read(MAX_FILE_SIZE_BYTES + 1)

    if not content:
        raise ValueError("Uploaded file is empty.")

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise ValueError("File exceeds the 10 MB upload limit.")

    if not _validate_file_signature(extension, content):
        raise ValueError("File content does not match its extension.")

    file_id = uuid4()
    safe_file_name = f"{file_id}{extension}"

    storage_key = f"submissions/{file_id}/{safe_file_name}"
    destination = UPLOAD_DIR / str(file_id) / safe_file_name
    temporary = destination.with_name(destination.name + ".tmp")

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Exclusive creation prevents accidental overwrite.
        with temporary.open("xb") as temp_file:
            temp_file.write(content)

        # Atomic rename within the same directory.
        temporary.replace(destination)

    except OSError:
        # Remove partial files if writing or renaming fails.
        for path in (temporary, destination):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

        try:
            destination.parent.rmdir()
        except OSError:
            pass

        raise ValueError("Unable to store the uploaded file.") from None

    return StoredFile(
        storage_key=storage_key,
        file_name=original_name,
        mime_type=mime_type,
        file_size_bytes=len(content),
    )


def delete_submission_file(storage_key: str) -> None:
    base_dir = UPLOAD_DIR.resolve()
    destination = (base_dir.parent / storage_key).resolve()

    if not destination.is_relative_to(base_dir):
        raise ValueError("Invalid storage key.")

    if destination.is_file():
        destination.unlink()

    parent = destination.parent

    if parent.is_dir() and parent != base_dir:
        try:
            parent.rmdir()
        except OSError:
            pass
