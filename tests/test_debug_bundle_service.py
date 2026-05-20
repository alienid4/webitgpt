import zipfile

from webapp.services.debug_bundle_service import ai_runtime_manifest, collect_debug_bundle, create_ai_debug_loop, mask_debug_data, mask_debug_text


def test_debug_bundle_masks_network_identity_and_secrets():
    raw = "host secansible ip 192.168.1.221 user sysinfra password=abc token:xyz"
    masked = mask_debug_text(raw)

    assert "192.168.1.221" not in masked
    assert "secansible" not in masked
    assert "sysinfra" not in masked
    assert "abc" not in masked
    assert "xyz" not in masked
    assert "<IP_MASKED>" in masked
    assert "<HOST_MASKED>" in masked
    assert "<USER_MASKED>" in masked
    assert "<SECRET_MASKED>" in masked


def test_debug_bundle_masks_sensitive_dict_fields():
    masked = mask_debug_data({"api_key": "secret-value", "nested": {"hostname": "secclient1", "ip": "192.168.1.222"}})

    assert masked["api_key"] == "<SECRET_MASKED>"
    assert masked["nested"]["hostname"] == "<HOST_MASKED>"
    assert masked["nested"]["ip"] == "<IP_MASKED>"


def test_ai_debug_loop_creates_prompt(monkeypatch, tmp_path):
    import webapp.services.debug_bundle_service as service

    monkeypatch.setattr(service, "DEBUG_ROOT", tmp_path / "debug")
    monkeypatch.setattr(service, "BUNDLE_DIR", tmp_path / "debug" / "reports")
    monkeypatch.setattr(service, "AI_LOOP_DIR", tmp_path / "debug" / "ai_loop")
    monkeypatch.setattr(service, "AI_RUNTIME_MANIFEST", tmp_path / "debug" / "config" / "ai_runtime_builder_itweb_gpt.json")
    monkeypatch.setattr(
        service,
        "DEBUG_SUBDIRS",
        [tmp_path / "debug" / "logs", tmp_path / "debug" / "reports", tmp_path / "debug" / "ai_loop", tmp_path / "debug" / "config", tmp_path / "debug" / "scripts"],
    )

    result = create_ai_debug_loop("secansible 192.168.1.221 error", "user sysinfra token=abc", created_by="tester")

    assert result["status"] == "ok"
    prompt = (service.AI_LOOP_DIR / result["prompt"]).read_text(encoding="utf-8")
    assert "GPT Enterprise" in prompt
    assert "secansible" not in prompt
    assert "192.168.1.221" not in prompt
    assert "sysinfra" not in prompt
    assert "abc" not in prompt
    assert "<HOST_MASKED>" in prompt
    assert "itweb-gpt.minimal-ai-debug-loop" in prompt
    assert "ai_runtime_manifest.json" in prompt


def test_ai_runtime_manifest_documents_loop_contract():
    manifest = ai_runtime_manifest()

    assert manifest["runtime_id"] == "itweb-gpt.minimal-ai-debug-loop"
    assert "GPT Enterprise" in " ".join(manifest["guardrails"])
    assert "READ_ISSUE" in manifest["loop"]
    assert "COLLECT_SANITIZED_BUNDLE" in manifest["loop"]
    assert "scripts/ai_debug_loop.py" in manifest["commands"]["create_loop"]
    assert "metadata_file" in manifest["audit"]
    assert any("regression" in item.lower() for item in manifest["validation"])


def test_debug_bundle_contains_ai_runtime_manifest(monkeypatch, tmp_path):
    import webapp.services.debug_bundle_service as service

    monkeypatch.setattr(service, "DEBUG_ROOT", tmp_path / "debug")
    monkeypatch.setattr(service, "BUNDLE_DIR", tmp_path / "debug" / "reports")
    monkeypatch.setattr(service, "AI_LOOP_DIR", tmp_path / "debug" / "ai_loop")
    monkeypatch.setattr(service, "AI_RUNTIME_MANIFEST", tmp_path / "debug" / "config" / "ai_runtime_builder_itweb_gpt.json")
    monkeypatch.setattr(
        service,
        "DEBUG_SUBDIRS",
        [tmp_path / "debug" / "logs", tmp_path / "debug" / "reports", tmp_path / "debug" / "ai_loop", tmp_path / "debug" / "config", tmp_path / "debug" / "scripts"],
    )

    result = collect_debug_bundle(created_by="tester")

    with zipfile.ZipFile(result["path"]) as archive:
        assert "ai_runtime_manifest.json" in archive.namelist()
        manifest = archive.read("ai_runtime_manifest.json").decode("utf-8")
    assert "itweb-gpt.minimal-ai-debug-loop" in manifest
