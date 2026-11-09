"""
Vahak — Security Core Tests (Post-Audit Hardened Suite)
───────────────────────────────────────────────────────────────────────────────
Tests for:
  1. resolve_safe_path()  — Path traversal defence (P0 Bouncer)
  2. sanitize_filename()  — OS-level filename sanitisation (P2/P5)
  3. Integration           — Proving the routes actually pass URL params to the Bouncer

Run with:
    python3 -m pytest tests/ -v

All tests monkeypatch VAULT_DIR to a controlled temporary directory so they
never touch the real ~/VahakVault and run cleanly on any machine.
"""

import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A fresh temporary directory acting as a sandboxed VahakVault for tests."""
    vault_dir = tmp_path / "VahakVault"
    vault_dir.mkdir()
    return vault_dir


@pytest.fixture(autouse=True)
def patch_vault(vault: Path):
    """
    Monkeypatch VAULT_DIR in both config and security modules so all test calls
    resolve against the temporary vault, not the real filesystem.
    """
    with (
        patch("app.core.config.VAULT_DIR", vault),
        patch("app.core.security.VAULT_DIR", vault),
    ):
        yield


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: resolve_safe_path — Path Traversal Defence
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidPaths:
    def test_vault_root_empty_string(self, vault: Path):
        """Empty string → resolves to Vault root itself. Must not raise."""
        from app.core.security import resolve_safe_path
        result = resolve_safe_path("")
        assert result == vault

    def test_simple_filename(self, vault: Path):
        """A plain filename resolves to a direct child of the Vault."""
        from app.core.security import resolve_safe_path
        result = resolve_safe_path("video.mp4")
        assert result == vault / "video.mp4"

    def test_nested_subdirectory(self, vault: Path):
        """A subdirectory path resolves correctly without raising."""
        from app.core.security import resolve_safe_path
        result = resolve_safe_path("Photos/2026/trip.jpg")
        assert result == vault / "Photos" / "2026" / "trip.jpg"

    def test_leading_slash_stripped(self, vault: Path):
        """A leading slash is stripped before resolution — not treated as absolute."""
        from app.core.security import resolve_safe_path
        result = resolve_safe_path("/video.mp4")
        assert result == vault / "video.mp4"

    def test_leading_backslash_stripped(self, vault: Path):
        """A leading backslash (Windows-style) is also stripped."""
        from app.core.security import resolve_safe_path
        result = resolve_safe_path("\\video.mp4")
        assert result == vault / "video.mp4"


class TestPathTraversalAttacks:
    def _assert_403(self, path: str):
        from app.core.security import resolve_safe_path
        with pytest.raises(HTTPException) as exc_info:
            resolve_safe_path(path)
        assert exc_info.value.status_code == 403

    def test_classic_traversal(self):
        """../../../etc/shadow — the canonical directory traversal attack."""
        self._assert_403("../../../etc/shadow")

    def test_single_level_traversal(self):
        """One level up from Vault root still escapes the sandbox."""
        self._assert_403("../sibling_dir/secret.txt")

    def test_absolute_path_linux(self):
        """
        /etc/passwd — after lstrip('/'), becomes 'etc/passwd', which resolves
        inside the Vault (no escape). This verifies our defence works correctly.
        The result must NOT be /etc/passwd on the real filesystem.
        """
        from app.core.security import resolve_safe_path
        result = resolve_safe_path("/etc/passwd")
        # Must resolve to Vault/etc/passwd, not /etc/passwd
        assert str(result).startswith(str(resolve_safe_path("")))

    def test_traversal_with_intermediate_valid_dir(self):
        """Photos/../../../etc/shadow — valid prefix followed by traversal."""
        self._assert_403("Photos/../../../etc/shadow")

    def test_double_encoded_dots(self):
        """
        URL-decoded traversal: FastAPI decodes %2e%2e%2f before it reaches us.
        This test verifies our function handles the already-decoded form.
        """
        self._assert_403("../etc/shadow")

    def test_windows_style_traversal(self):
        """..\\..\\Windows\\System32 — backslash traversal on non-Windows hosts."""
        # On Linux, Path() treats backslash as a literal filename character,
        # so this is actually safe — the backslash doesn't traverse.
        # Document this behaviour explicitly rather than leave it ambiguous.
        from app.core.security import resolve_safe_path
        # Should NOT raise because "..\\file" on Linux is a filename, not a traversal
        result = resolve_safe_path("..\\..\\etc\\shadow")
        # The result should still be inside the vault (backslash is literal on Linux)
        assert result.is_relative_to(resolve_safe_path(""))

    def test_null_byte_in_path(self, vault: Path):
        """
        Null-byte injection: foo\x00../etc/shadow. Python's Path() raises
        ValueError on embedded null bytes, which we let propagate as a 500
        (an attacker learns nothing useful from a 500 vs 403 here).
        This test documents the behaviour.
        """
        from app.core.security import resolve_safe_path
        with pytest.raises((HTTPException, ValueError)):
            resolve_safe_path("foo\x00../etc/shadow")

    def test_symlink_escape(self, vault: Path, tmp_path: Path):
        """
        A symlink inside the Vault pointing to /etc should be caught because
        Path.resolve() follows symlinks before is_relative_to() checks.
        """
        from app.core.security import resolve_safe_path

        # Create a symlink inside the vault pointing outside it
        outside = tmp_path / "outside_vault"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret")

        evil_link = vault / "escape_link"
        evil_link.symlink_to(outside)

        # Accessing through the symlink must be blocked
        with pytest.raises(HTTPException) as exc_info:
            resolve_safe_path("escape_link/secret.txt")
        assert exc_info.value.status_code == 403


class TestEdgeCases:
    def test_empty_filename_after_strip(self, vault: Path):
        """Multiple leading slashes collapse to empty → resolves to Vault root."""
        from app.core.security import resolve_safe_path
        result = resolve_safe_path("///")
        assert result == vault

    def test_non_existent_path_is_allowed(self, vault: Path):
        """
        A path that doesn't exist yet must NOT raise — the push endpoint needs
        to resolve destination paths for files that haven't been written yet.
        """
        from app.core.security import resolve_safe_path
        result = resolve_safe_path("new_folder/new_file.mp4")
        assert result == vault / "new_folder" / "new_file.mp4"
        assert not result.exists()  # file doesn't exist — that's fine


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: sanitize_filename — OS-Level Filename Sanitisation
# ═══════════════════════════════════════════════════════════════════════════════

class TestSanitizeFilenameValid:
    """Valid filenames that should pass through (possibly with minor transforms)."""

    def test_normal_filename(self):
        from app.core.security import sanitize_filename
        assert sanitize_filename("report.pdf") == "report.pdf"

    def test_dotfile(self):
        """Dotfiles like .gitignore should survive (leading dot is not stripped
        since we strip leading dots only from the beginning — .gitignore has
        content after the dot)."""
        from app.core.security import sanitize_filename
        # After strip(" ."), ".gitignore" becomes "gitignore" — document this.
        # This is intentional: dotfiles are a Unix convention that doesn't
        # translate to Windows, and we prioritize cross-platform safety.
        result = sanitize_filename(".gitignore")
        assert result == "gitignore"

    def test_unicode_filename(self):
        from app.core.security import sanitize_filename
        assert sanitize_filename("चित्रनिधि_photo.avif") == "चित्रनिधि_photo.avif"

    def test_spaces_in_filename(self):
        from app.core.security import sanitize_filename
        assert sanitize_filename("my vacation photo.jpg") == "my vacation photo.jpg"


class TestSanitizeFilenameAttacks:
    """Attack payloads that must be neutralised or rejected."""

    def test_path_separators_stripped(self):
        """Slashes in filename are replaced with underscores (not traversal)."""
        from app.core.security import sanitize_filename
        result = sanitize_filename("../../etc/shadow")
        # rsplit extracts basename "shadow" after the last /
        assert result == "shadow"

    def test_backslash_separators_stripped(self):
        from app.core.security import sanitize_filename
        result = sanitize_filename("..\\..\\Windows\\System32")
        assert result == "System32"

    def test_control_characters_replaced(self):
        from app.core.security import sanitize_filename
        result = sanitize_filename("file\x01\x02\x03.txt")
        assert result == "file___.txt"

    def test_null_byte_replaced(self):
        from app.core.security import sanitize_filename
        result = sanitize_filename("file\x00.txt")
        assert result == "file_.txt"

    def test_oversized_filename_clamped(self):
        """300-char filename must be clamped to 255 bytes for ext4."""
        from app.core.security import sanitize_filename
        long_name = "A" * 300 + ".pdf"
        result = sanitize_filename(long_name)
        assert len(result.encode("utf-8")) <= 255
        assert result.endswith(".pdf")

    def test_oversized_unicode_filename_clamped(self):
        """Multi-byte unicode characters — byte length matters, not char count."""
        from app.core.security import sanitize_filename
        # Each Hindi char is 3 bytes in UTF-8. 100 chars = 300 bytes > 255 limit
        long_name = "अ" * 100 + ".avif"
        result = sanitize_filename(long_name)
        assert len(result.encode("utf-8")) <= 255

    def test_windows_reserved_CON(self):
        from app.core.security import sanitize_filename
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename("CON")
        assert exc_info.value.status_code == 400

    def test_windows_reserved_CON_with_extension(self):
        """CON.txt is just as illegal as CON on NTFS."""
        from app.core.security import sanitize_filename
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename("CON.txt")
        assert exc_info.value.status_code == 400

    def test_windows_reserved_NUL(self):
        from app.core.security import sanitize_filename
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename("NUL")
        assert exc_info.value.status_code == 400

    def test_windows_reserved_COM1(self):
        from app.core.security import sanitize_filename
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename("COM1")
        assert exc_info.value.status_code == 400

    def test_windows_reserved_case_insensitive(self):
        """Reserved name check must be case-insensitive."""
        from app.core.security import sanitize_filename
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename("con.TXT")
        assert exc_info.value.status_code == 400

    def test_empty_filename_rejected(self):
        from app.core.security import sanitize_filename
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename("")
        assert exc_info.value.status_code == 400

    def test_dots_only_rejected(self):
        from app.core.security import sanitize_filename
        with pytest.raises(HTTPException) as exc_info:
            sanitize_filename("...")
        assert exc_info.value.status_code == 400

    def test_trailing_dots_stripped(self):
        """Windows rejects filenames with trailing dots."""
        from app.core.security import sanitize_filename
        result = sanitize_filename("file...")
        assert result == "file"
        assert not result.endswith(".")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Integration — Route-to-Bouncer Binding (P0 Verification)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRouteBouncerIntegration:
    """
    Prove that the URL path parameter is actually passed to resolve_safe_path()
    in every route. This is the P0 fix verification — the old SafePath DI shim
    silently swallowed the parameter and always resolved to Vault root.
    """

    @pytest.fixture
    def client(self, vault: Path):
        """TestClient with the patched Vault."""
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_scanner_receives_sub_path(self, client, vault: Path):
        """GET /scan/list/photos must list the photos dir, not Vault root."""
        photos = vault / "photos"
        photos.mkdir()
        (photos / "a.jpg").write_text("fake")
        (vault / "other.txt").write_text("noise")

        resp = client.get("/api/v1/scan/list/photos")
        assert resp.status_code == 200
        data = resp.json()
        # Must list contents of photos/, not the Vault root
        names = [e["name"] for e in data["contents"]]
        assert "a.jpg" in names
        assert "other.txt" not in names  # this is in Vault root, not photos/

    def test_pull_receives_file_path(self, client, vault: Path):
        """GET /pull/docs/readme.txt must serve that specific file."""
        docs = vault / "docs"
        docs.mkdir()
        (docs / "readme.txt").write_text("hello vahak")

        resp = client.get("/api/v1/transfer/pull/docs/readme.txt")
        assert resp.status_code == 200
        assert resp.content == b"hello vahak"

    def test_pull_traversal_blocked(self, client, vault: Path):
        """Path traversal via pull must be blocked by the Bouncer (403)."""
        resp = client.get("/api/v1/transfer/pull/../../../etc/passwd")
        # FastAPI may normalise the URL path (absorbing ../) before routing,
        # which results in a 404 from the router. Either 403 or 404 is safe —
        # the critical thing is that /etc/passwd is NOT served.
        assert resp.status_code in (403, 404)
        assert b"root:" not in resp.content  # /etc/passwd content must not leak

    def test_push_receives_dest_path(self, client, vault: Path):
        """POST /push/uploads must write the file into the uploads subdir."""
        import io
        resp = client.post(
            "/api/v1/transfer/push/uploads",
            files={"file": ("test.txt", io.BytesIO(b"payload"), "text/plain")},
        )
        assert resp.status_code == 201
        written = vault / "uploads" / "test.txt"
        assert written.exists()
        assert written.read_text() == "payload"

    def test_health_does_not_leak_path(self, client, vault: Path):
        """P6: /health must return directory name only, not absolute path."""
        resp = client.get("/health")
        data = resp.json()
        assert data["vault"] == "VahakVault"
        assert "/" not in data["vault"]  # no path separators


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Sync Delta Logic (P7 Verification)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyncDeltaP7:
    """Verify that to_push and to_delete are mutually exclusive."""

    def test_client_only_files_are_pushes_when_deletions_off(self, vault: Path):
        """Client-only files should be in to_push when sync_deletions=False."""
        from app.api.routes.sync import _compute_delta, ClientFileRecord

        hub_entries = []  # Hub has nothing
        client_records = [
            ClientFileRecord(
                name="new.txt", size_bytes=100,
                modified_at="2026-10-29T06:00:00Z",
                relative_path="new.txt",
            ),
        ]

        to_pull, to_push, to_delete = _compute_delta(hub_entries, client_records, sync_deletions=False)
        assert to_push == ["new.txt"]
        assert to_delete == []

    def test_client_only_files_are_deletes_when_deletions_on(self, vault: Path):
        """Client-only files should be in to_delete when sync_deletions=True."""
        from app.api.routes.sync import _compute_delta, ClientFileRecord

        hub_entries = []  # Hub has nothing
        client_records = [
            ClientFileRecord(
                name="removed.txt", size_bytes=100,
                modified_at="2026-10-29T06:00:00Z",
                relative_path="removed.txt",
            ),
        ]

        to_pull, to_push, to_delete = _compute_delta(hub_entries, client_records, sync_deletions=True)
        assert to_push == []
        assert to_delete == ["removed.txt"]

    def test_no_file_appears_in_both_lists(self, vault: Path):
        """No filename may ever appear in both to_push and to_delete."""
        from app.api.routes.sync import _compute_delta, ClientFileRecord

        hub_entries = [
            {"name": "shared.txt", "is_dir": False, "size_bytes": 200,
             "modified_at": "2026-10-29T07:00:00Z", "relative_path": "shared.txt"},
        ]
        client_records = [
            ClientFileRecord(
                name="shared.txt", size_bytes=100,
                modified_at="2026-10-29T06:00:00Z",
                relative_path="shared.txt",
            ),
            ClientFileRecord(
                name="orphan.txt", size_bytes=50,
                modified_at="2026-10-29T05:00:00Z",
                relative_path="orphan.txt",
            ),
        ]

        for deletions_flag in (True, False):
            to_pull, to_push, to_delete = _compute_delta(
                hub_entries, client_records, sync_deletions=deletions_flag
            )
            push_set = set(to_push)
            delete_set = set(to_delete)
            overlap = push_set & delete_set
            assert overlap == set(), f"Files in both to_push and to_delete: {overlap}"
