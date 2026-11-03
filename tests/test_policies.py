import json
from pathlib import Path

import pytest

from src.policies.catalog import PolicyService, normalize_query


def write_catalog(path: Path, version: str = "2.1", hours_content: str = "Segunda a sexta: 09:00 às 18:00.") -> None:
    policy = {
        "version": version,
        "source_transcript": "data/policies/politicas-da-loja.md",
        "sections": [
            {
                "id": "2",
                "title": "Horário de Funcionamento",
                "content": hours_content,
                "source": {"path": "data/policies/politicas-da-loja.md", "pages": [2]},
                "version": version,
                "topics": ["hours"],
            },
            {
                "id": "3",
                "title": "Formas de Pagamento",
                "content": "PIX à vista com desconto.",
                "source": {"path": "data/policies/politicas-da-loja.md", "pages": [3]},
                "version": version,
                "topics": ["payments"],
            },
            {
                "id": "1",
                "title": "Sobre a Empório da Música",
                "content": "Telefone: 111.",
                "source": {"path": "data/policies/politicas-da-loja.md", "pages": [2]},
                "version": version,
                "topics": ["contact"],
            },
            {
                "id": "7",
                "title": "Atendimento via WhatsApp",
                "content": "WhatsApp: 222.",
                "source": {"path": "data/policies/politicas-da-loja.md", "pages": [6]},
                "version": version,
                "topics": ["contact"],
            },
        ],
        "topics": [
            {"id": "hours", "aliases": ["horário", "horário de funcionamento"], "sections": ["2"]},
            {"id": "payments", "aliases": ["pagamento", "pix", "formas de pagamento"], "sections": ["3"]},
            {"id": "contact", "aliases": ["telefone"], "sections": ["1", "7"]},
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "policies.json"
    write_catalog(path)
    return path


def test_full_copy_normalization_multi_topic_conflict_and_unknown() -> None:
    copied = Path("data/policies/politicas-da-loja.md")
    assert "## 1. Sobre a Empório da Música" in copied.read_text(encoding="utf-8")
    assert "## 10. Disposições Finais" in copied.read_text(encoding="utf-8")
    assert normalize_query("  HORÁRIO\tde funcionamento?  ") == "horario de funcionamento"
    assert normalize_query("R$ 500,00!") == "r$ 500,00"
    assert normalize_query("10% de desconto.") == "10% de desconto"

    service = PolicyService(Path("data/policies/policies.json"))
    assert len(service._sections) == 10
    assert service._sections["4"].title == "Política de Trocas e Devoluções"
    assert service._sections["4"].source_path == "data/policies/politicas-da-loja.md"
    assert service._sections["4"].pages
    conflict = service.lookup("horário e telefone?")
    unknown = service.lookup("meu pedido")
    assert {section.id for section in conflict.sections} == {"1", "2", "7"}
    assert unknown.status == "not_found"
    assert unknown.sections == ()


def test_cache_only_stores_exact_public_faq_not_context(catalog_path: Path) -> None:
    service = PolicyService(catalog_path)

    first = service.lookup("QUAL É O HORÁRIO DA LOJA?")
    second = service.lookup("qual e o horario da loja")
    before = service.cache_info()
    contextual = service.lookup("horário meu email pessoa@example.com")

    assert first.status == "ok"
    assert [section.id for section in first.sections] == ["2"]
    assert first is second
    assert contextual.status == "ok"
    assert service.cache_info() == before
    assert before.maxsize == 128
    assert before.misses == 1
    assert before.hits == 1


def test_catalog_change_invalidates_cached_result_and_alias_uses_token_boundary(catalog_path: Path) -> None:
    service = PolicyService(catalog_path)
    first = service.lookup("horario")
    assert first.sections[0].content.startswith("Segunda a sexta")
    assert service.lookup("pixar").status == "not_found"

    write_catalog(catalog_path, version="2.2", hours_content="Horário atualizado.")
    updated = service.lookup("horario")

    assert updated.sections[0].content == "Horário atualizado."
    assert service.cache_info().currsize == 1
    assert service.cache_info().misses == 1
