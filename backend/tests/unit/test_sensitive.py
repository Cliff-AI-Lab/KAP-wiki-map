"""M1 #1 · 敏感实体识别 + 脱敏管线单测（决策书 §5.4 D10/D11）。"""

from __future__ import annotations

import base64
import os

import pytest

from packages.common import settings
from packages.sensitive import (
    MappingStoreError,
    PrecisionLevel,
    SensitiveCategory,
    SensitiveMappingStore,
    detect_sensitive_spans,
    redact_document,
)
from packages.sensitive.mapping_store import (
    _load_aes_key,
    reset_mapping_store_for_test,
)


# ════════════════════════════════════════════════════════════════════════
#  NER
# ════════════════════════════════════════════════════════════════════════


class TestPersonNameNER:
    def test_zhang_gong_detected(self) -> None:
        spans = detect_sensitive_spans("张工负责本项目")
        cats = [s.category for s in spans]
        assert SensitiveCategory.PERSON_NAME in cats

    def test_li_zong_detected(self) -> None:
        spans = detect_sensitive_spans("李总今天来检查")
        names = [s for s in spans if s.category == SensitiveCategory.PERSON_NAME]
        assert any(s.text == "李总" for s in names)

    def test_two_char_name_with_title(self) -> None:
        spans = detect_sensitive_spans("陈小华博士做了报告")
        names = [s.text for s in spans if s.category == SensitiveCategory.PERSON_NAME]
        assert "陈小华博士" in names

    def test_no_false_positive_pure_text(self) -> None:
        spans = detect_sensitive_spans("这是一段普通文本，无任何人名")
        names = [s for s in spans if s.category == SensitiveCategory.PERSON_NAME]
        assert names == []


class TestProcessParamNER:
    def test_temperature_detected(self) -> None:
        spans = detect_sensitive_spans("轴承温度不超过80℃")
        params = [s for s in spans if s.category == SensitiveCategory.PROCESS_PARAM]
        assert len(params) == 1
        assert params[0].extra["unit"] == "℃"
        assert params[0].extra["value"] == "80"

    def test_pressure_with_decimal(self) -> None:
        spans = detect_sensitive_spans("压力 1.5 MPa")
        params = [s for s in spans if s.category == SensitiveCategory.PROCESS_PARAM]
        assert any("MPa" in s.text for s in params)

    def test_range_value(self) -> None:
        spans = detect_sensitive_spans("转速 1500-1800 r/min")
        params = [s for s in spans if s.category == SensitiveCategory.PROCESS_PARAM]
        assert len(params) >= 1

    def test_voltage(self) -> None:
        spans = detect_sensitive_spans("电压 380V")
        params = [s for s in spans if s.category == SensitiveCategory.PROCESS_PARAM]
        assert any("380V" in s.text for s in params)


class TestClientNameNER:
    def test_whitelist_match(self) -> None:
        spans = detect_sensitive_spans(
            "我们与上海某电厂签订了合同",
            client_whitelist=("上海某电厂",),
        )
        clients = [s for s in spans if s.category == SensitiveCategory.CLIENT_NAME]
        assert len(clients) == 1

    def test_no_match_when_empty_whitelist(self) -> None:
        spans = detect_sensitive_spans("我们与上海某电厂合作")
        clients = [s for s in spans if s.category == SensitiveCategory.CLIENT_NAME]
        assert clients == []

    def test_no_overlap(self) -> None:
        """长客户名优先匹配，避免子串重复检出。"""
        spans = detect_sensitive_spans(
            "上海某电厂的设备",
            client_whitelist=("上海某电厂", "电厂"),
        )
        clients = [s for s in spans if s.category == SensitiveCategory.CLIENT_NAME]
        assert len(clients) == 1
        assert clients[0].text == "上海某电厂"


# ════════════════════════════════════════════════════════════════════════
#  Redactor
# ════════════════════════════════════════════════════════════════════════


class TestRedactPersonName:
    def test_zhang_gong_to_engineer(self) -> None:
        result = redact_document("张工负责本项目")
        assert "张工" not in result.redacted_text
        assert "工程师A" in result.redacted_text

    def test_consistent_across_occurrences(self) -> None:
        """同一个人名出现多次 → 同一替换 token（一致性 §5.4）。"""
        result = redact_document("张工说，张工又说一次")
        # 两处张工应该都替换为同一 token
        # （原文 "张工说，张工又说一次" → 替换后两处相同）
        assert result.redacted_text.count("工程师A") == 2


class TestRedactProcessParam:
    def test_interval_default(self) -> None:
        result = redact_document("温度 100℃")
        assert "100℃" not in result.redacted_text
        # 区间 ±10% → [90.0-110.0℃]
        assert "[" in result.redacted_text and "℃]" in result.redacted_text

    def test_exact_keeps_value(self) -> None:
        result = redact_document(
            "温度 100℃", precision=PrecisionLevel.EXACT,
        )
        # EXACT 不脱敏数值（仍打 token，但占位符 = 原文）
        assert "100℃" in result.redacted_text

    def test_level_grades(self) -> None:
        result = redact_document(
            "压力 200 MPa", precision=PrecisionLevel.LEVEL,
        )
        assert "[高MPa]" in result.redacted_text or "[" in result.redacted_text


class TestRedactClient:
    def test_codification(self) -> None:
        result = redact_document(
            "上海某电厂签订合同",
            client_whitelist=("上海某电厂",),
        )
        assert "上海某电厂" not in result.redacted_text
        assert "客户A001" in result.redacted_text

    def test_two_clients_distinct_codes(self) -> None:
        result = redact_document(
            "上海某电厂和北京某厂",
            client_whitelist=("上海某电厂", "北京某厂"),
        )
        assert "客户A001" in result.redacted_text
        assert "客户A002" in result.redacted_text


class TestMappingTokens:
    def test_tokens_recorded(self) -> None:
        result = redact_document("张工负责")
        assert len(result.tokens) >= 1
        tok = result.tokens[0]
        assert tok.original == "张工"
        assert tok.mapping_id  # stable id 必须有

    def test_stable_mapping_id_across_runs(self) -> None:
        """同一原文两次脱敏 → 同一 mapping_id。"""
        r1 = redact_document("张工")
        r2 = redact_document("张工")
        assert r1.tokens[0].mapping_id == r2.tokens[0].mapping_id


# ════════════════════════════════════════════════════════════════════════
#  Mapping Store
# ════════════════════════════════════════════════════════════════════════


_TEST_KEY_HEX = "a" * 64  # 32 字节


@pytest.fixture
def _aes_key():
    return bytes.fromhex(_TEST_KEY_HEX)


class TestMappingStoreMemory:
    async def test_put_and_get(self, _aes_key) -> None:
        store = SensitiveMappingStore(aes_key=_aes_key)
        await store.initialize()

        await store.put("p_abc123", "张工", meta={"role": "工程师"})
        result = await store.get("p_abc123")
        assert result is not None
        assert result["original"] == "张工"
        assert result["meta"]["role"] == "工程师"

    async def test_has_check(self, _aes_key) -> None:
        store = SensitiveMappingStore(aes_key=_aes_key)
        await store.initialize()

        await store.put("p_xyz", "李总")
        assert await store.has("p_xyz") is True
        assert await store.has("p_missing") is False

    async def test_overwrite(self, _aes_key) -> None:
        store = SensitiveMappingStore(aes_key=_aes_key)
        await store.initialize()

        await store.put("k1", "v1")
        await store.put("k1", "v2")
        assert (await store.get("k1"))["original"] == "v2"

    async def test_aes_encryption_actually_encrypts(self, _aes_key) -> None:
        """加密后的 blob 不含原文。"""
        store = SensitiveMappingStore(aes_key=_aes_key)
        await store.initialize()
        await store.put("k", "敏感原文")
        # 直接读内存的 blob
        full_key = store._full_key("k")
        blob = store._memory[full_key]
        assert b"\xe6\x95\x8f\xe6" not in blob  # "敏" 的 UTF-8 不应在密文里


class TestAESKeyLoading:
    def test_hex_key(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "sensitive_aes_key", _TEST_KEY_HEX)
        key = _load_aes_key()
        assert len(key) == 32

    def test_base64_key(self, monkeypatch) -> None:
        b64 = base64.b64encode(b"a" * 32).decode("ascii")
        monkeypatch.setattr(settings, "sensitive_aes_key", b64)
        key = _load_aes_key()
        assert len(key) == 32

    def test_empty_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "sensitive_aes_key", "")
        assert _load_aes_key() is None

    def test_wrong_length_raises(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "sensitive_aes_key", "ab" * 16)  # 16 字节 ≠ 32
        with pytest.raises(MappingStoreError, match="32 字节"):
            _load_aes_key()


# ════════════════════════════════════════════════════════════════════════
#  端到端
# ════════════════════════════════════════════════════════════════════════


class TestEndToEnd:
    async def test_redact_then_decode_roundtrip(self, _aes_key) -> None:
        """脱敏 → 入 mapping store → 按 mapping_id 解码回原文。"""
        store = SensitiveMappingStore(aes_key=_aes_key)
        await store.initialize()

        text = "张工负责，温度 80℃"
        result = redact_document(text)

        # 把 token 写进 store（M2 W4 hook 做的事）
        for tok in result.tokens:
            await store.put(tok.mapping_id, tok.original, meta={"category": tok.category.value})

        # 高密用户解码
        for tok in result.tokens:
            decoded = await store.get(tok.mapping_id)
            assert decoded["original"] == tok.original
