# SERVICE: SAGE Secure File Storage
# Local development storage plus S3/R2-compatible production object storage, tenant prefixes, immutable hashes and time-limited access.

import hashlib
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path
from flask import redirect, send_file
from werkzeug.utils import secure_filename
from models import Attachment
from packages.database import db

ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}


def _s3_client(app):
    try: import boto3
    except ImportError as error: raise RuntimeError("S3/R2 storage requires boto3. Run pip install -r requirements.txt.") from error
    kwargs = {"region_name": app.config.get("S3_REGION") or "auto"}
    if app.config.get("S3_ENDPOINT_URL"): kwargs["endpoint_url"] = app.config["S3_ENDPOINT_URL"]
    if app.config.get("S3_ACCESS_KEY_ID"): kwargs["aws_access_key_id"] = app.config["S3_ACCESS_KEY_ID"]
    if app.config.get("S3_SECRET_ACCESS_KEY"): kwargs["aws_secret_access_key"] = app.config["S3_SECRET_ACCESS_KEY"]
    return boto3.client("s3", **kwargs)


def _safe_upload(file_storage, app):
    original = secure_filename(file_storage.filename) or "document"; extension = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if extension not in ALLOWED_EXTENSIONS: raise ValueError("Only PDF, PNG, JPG, JPEG and WEBP files are allowed.")
    raw = file_storage.read(); max_bytes = int(app.config.get("MAX_UPLOAD_MB", 12)) * 1024 * 1024
    if not raw: raise ValueError("The uploaded file is empty.")
    if len(raw) > max_bytes: raise ValueError(f"File is larger than the {app.config.get('MAX_UPLOAD_MB', 12)} MB limit.")
    return original, extension, raw, hashlib.sha256(raw).hexdigest()


def save_attachment(app, file_storage, user, entity_type, entity_id, kind="document", final=False):
    if not file_storage or not file_storage.filename: return None
    original, extension, raw, digest = _safe_upload(file_storage, app); duplicate = Attachment.query.filter_by(organization_id=user.organization_id, sha256=digest, is_final=True).first()
    if duplicate and final: raise ValueError("This receipt/document has already been used as final evidence in this organization.")

    now = datetime.now(timezone.utc); stored_name = f"{uuid.uuid4().hex}.{extension}"; relative = Path("uploads") / kind / user.organization_id / f"{now.year:04d}" / f"{now.month:02d}" / stored_name; backend = str(app.config.get("STORAGE_BACKEND") or "local").lower()
    if backend in {"s3", "r2", "object"}:
        bucket = app.config.get("S3_BUCKET")
        if not bucket: raise RuntimeError("S3_BUCKET is required when SAGE_STORAGE_BACKEND is s3/r2.")
        key = relative.as_posix(); _s3_client(app).put_object(Bucket=bucket, Key=key, Body=raw, ContentType=file_storage.mimetype or "application/octet-stream", Metadata={"organization-id": user.organization_id, "sha256": digest}); stored_path = f"s3:{key}"
    else:
        target = Path(app.config["STORAGE_DIR"]) / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw); stored_path = relative.as_posix()

    attachment = Attachment(organization_id=user.organization_id, uploaded_by_id=user.id, entity_type=entity_type, entity_id=entity_id, kind=kind, original_name=original, stored_path=stored_path, mime_type=file_storage.mimetype, file_size=len(raw), sha256=digest, is_final=bool(final)); db.session.add(attachment); return attachment


def attachment_response(app, attachment):
    """Serve local evidence or redirect to a short-lived private object-storage URL."""
    stored_path = str(attachment.stored_path or "")
    if stored_path.startswith("s3:"):
        bucket = app.config.get("S3_BUCKET")
        if not bucket: raise FileNotFoundError("Object-storage bucket is not configured.")
        key = stored_path[3:]; url = _s3_client(app).generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key, "ResponseContentDisposition": f'inline; filename="{attachment.original_name}"'}, ExpiresIn=int(app.config.get("S3_PRESIGNED_SECONDS", 300))); return redirect(url)
    path = Path(app.config["STORAGE_DIR"]) / stored_path
    if not path.exists() or not path.is_file(): raise FileNotFoundError("Evidence file is unavailable.")
    return send_file(path, mimetype=attachment.mime_type, download_name=attachment.original_name, as_attachment=False)


def delete_attachment_file(app, attachment):
    """Best-effort physical deletion used by irreversible platform-owner deletion."""
    stored_path = str(attachment.stored_path or "")
    if stored_path.startswith("s3:"):
        bucket = app.config.get("S3_BUCKET")
        if bucket:
            try: _s3_client(app).delete_object(Bucket=bucket, Key=stored_path[3:])
            except Exception as error: app.logger.warning("Could not delete object-storage evidence %s: %s", attachment.id, error)
        return
    try:
        path = Path(app.config["STORAGE_DIR"]) / stored_path
        if path.exists() and path.is_file(): path.unlink()
    except Exception as error: app.logger.warning("Could not delete local evidence %s: %s", attachment.id, error)
