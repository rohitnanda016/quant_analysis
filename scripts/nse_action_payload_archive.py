"""Archive raw NSE corporate-action HTTP response bodies and provenance."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def _timestamp_slug(value):
    return str(value).replace("-", "").replace(":", "").replace(".", "").replace("+00:00", "Z")


def archive_http_response(response, raw_archive_dir, chunk_index, start_date, end_date,
                          attempt, requested_at_utc=None):
    """Save response.content verbatim before JSON parsing (requests-decoded bytes)."""
    root = Path(raw_archive_dir)
    root.mkdir(parents=True, exist_ok=True)
    body = bytes(response.content)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    content_type = str(response.headers.get("Content-Type", ""))
    json_body = "json" in content_type.lower() or body.lstrip().startswith((b"{", b"["))
    suffix = ".json" if json_body else ".body"
    stem = (
        f"chunk-{int(chunk_index):03d}_{start_date}_{end_date}"
        f"_attempt-{int(attempt):02d}_{_timestamp_slug(retrieved_at)}"
    )
    body_name = stem + suffix
    metadata_name = stem + ".metadata.json"
    (root / body_name).write_bytes(body)
    record = {
        "source": "https://www.nseindia.com/api/corporates-corporateActions",
        "method": "GET",
        "request_url": str(getattr(response, "url", "")),
        "http_status": int(response.status_code),
        "requested_at_utc": requested_at_utc,
        "retrieved_at_utc": retrieved_at,
        "content_type": content_type,
        "response_body_file": body_name,
        "response_body_bytes": len(body),
        "response_body_sha256": hashlib.sha256(body).hexdigest(),
        "hash_scope": "response.content bytes exposed by Python requests before JSON parsing/normalization; not compressed wire bytes",
        "chunk_index": int(chunk_index),
        "requested_start": str(start_date),
        "requested_end": str(end_date),
        "attempt": int(attempt),
    }
    (root / metadata_name).write_text(json.dumps(record, indent=2), encoding="utf-8")
    record["metadata_file"] = metadata_name
    return record


def write_manifest(raw_archive_dir, records, retrieval_complete, source,
                   requested_start, requested_end):
    """Write a reproducible manifest listing all archived HTTP response attempts."""
    root = Path(raw_archive_dir)
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "source": str(source),
        "requested_start": str(requested_start),
        "requested_end": str(requested_end),
        "retrieval_complete": bool(retrieval_complete),
        "response_attempt_count": int(len(records)),
        "successful_http_200_count": sum(int(r.get("http_status", 0) == 200) for r in records),
        "responses": list(records),
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": "Each listed response body was saved before parsing/normalization; SHA-256 applies to requests-exposed response.content bytes, not the compressed wire stream.",
    }
    path = root / "manifest.json"
    temporary = root / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temporary.replace(path)
    return str(path)
