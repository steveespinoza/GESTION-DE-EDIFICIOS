from urllib.parse import parse_qs, urlsplit

import boto3
from botocore.config import Config
from botocore.stub import Stubber

from app.storage.s3 import S3FileStorage


def test_s3_put_is_private_and_download_is_signed_as_attachment():
    client = boto3.session.Session(
        aws_access_key_id="synthetic-testing-key",
        aws_secret_access_key="synthetic-testing-secret",
    ).client("s3", region_name="us-east-1", config=Config(signature_version="s3v4"))
    storage = S3FileStorage(client, "edificios-synthetic-test")
    key = "invoice-files/fixture/document/digest"
    body = b"%PDF-1.7\nFixture"
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": storage.bucket,
                "Key": key,
                "Body": body,
                "ContentType": "application/pdf",
                "CacheControl": "private, no-store",
            },
        )
        storage.put(key, body, "application/pdf")
        url = storage.download_url(key, "Facturación.pdf")
        stub.assert_no_pending_responses()

    parts = urlsplit(url)
    query = parse_qs(parts.query)
    assert parts.scheme == "https"
    assert parts.path.endswith(key)
    assert query["X-Amz-Expires"] == ["300"]
    assert "X-Amz-Signature" in query
    assert query["response-content-type"] == ["application/octet-stream"]
    disposition = query["response-content-disposition"][0]
    assert disposition.startswith("attachment;")
    assert "Facturaci%C3%B3n.pdf" in disposition
