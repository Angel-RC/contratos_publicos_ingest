import requests

from descargas import RemoteFile, download_files


class FakeResponse:
    def __init__(self, chunks: list[bytes], status_code: int = 200, headers: dict | None = None):
        self._chunks = chunks
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "application/zip"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)

    def iter_content(self, chunk_size: int):
        yield from self._chunks


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse]):
        self._responses = responses
        self.requested_urls: list[str] = []

    def get(self, url, timeout=None, stream=None):
        self.requested_urls.append(url)
        return self._responses[url]


def test_download_files_writes_new_file(tmp_path):
    remote_file = RemoteFile(name="a.zip", url="https://example.com/a.zip", year=2024)
    session = FakeSession({remote_file.url: FakeResponse([b"hello", b"world"])})

    downloaded = download_files([remote_file], tmp_path, session=session)

    assert downloaded == [tmp_path / "a.zip"]
    assert (tmp_path / "a.zip").read_bytes() == b"helloworld"


def test_download_files_skips_existing_file_by_default(tmp_path):
    existing = tmp_path / "a.zip"
    existing.write_bytes(b"already here")
    remote_file = RemoteFile(name="a.zip", url="https://example.com/a.zip", year=2024)
    session = FakeSession({remote_file.url: FakeResponse([b"new content"])})

    downloaded = download_files([remote_file], tmp_path, session=session)

    assert downloaded == [existing]
    assert existing.read_bytes() == b"already here"
    assert session.requested_urls == []


def test_download_files_overwrites_existing_file_when_requested(tmp_path):
    existing = tmp_path / "a.zip"
    existing.write_bytes(b"already here")
    remote_file = RemoteFile(name="a.zip", url="https://example.com/a.zip", year=2024)
    session = FakeSession({remote_file.url: FakeResponse([b"new content"])})

    downloaded = download_files([remote_file], tmp_path, overwrite=True, session=session)

    assert downloaded == [existing]
    assert existing.read_bytes() == b"new content"


def test_download_files_skips_file_not_found(tmp_path):
    remote_file = RemoteFile(name="missing.zip", url="https://example.com/missing.zip", year=2024)
    session = FakeSession({remote_file.url: FakeResponse([], status_code=404)})

    downloaded = download_files([remote_file], tmp_path, session=session)

    assert downloaded == []
    assert not (tmp_path / "missing.zip").exists()


def test_download_files_skips_html_error_page(tmp_path):
    remote_file = RemoteFile(name="future.zip", url="https://example.com/future.zip", year=2026)
    html_page = FakeResponse([b"<html>certificado no autorizado</html>"], headers={"Content-Type": "text/html; charset=UTF-8"})
    session = FakeSession({remote_file.url: html_page})

    downloaded = download_files([remote_file], tmp_path, session=session)

    assert downloaded == []
    assert not (tmp_path / "future.zip").exists()


class FlakyThenOkSession:
    def __init__(self, response: FakeResponse):
        self._response = response
        self.calls = 0

    def get(self, url, timeout=None, stream=None):
        self.calls += 1
        if self.calls == 1:
            raise requests.exceptions.ConnectionError("boom")
        return self._response


def test_download_files_retries_transient_errors_before_succeeding(tmp_path):
    remote_file = RemoteFile(name="a.zip", url="https://example.com/a.zip", year=2024)
    session = FlakyThenOkSession(FakeResponse([b"ok"]))

    downloaded = download_files([remote_file], tmp_path, session=session)

    assert downloaded == [tmp_path / "a.zip"]
    assert session.calls == 2
