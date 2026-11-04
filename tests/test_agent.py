from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.genai import types

from src.agent.service import AgentService
from src.data.repositories import DemoIdentity, OrderItemSummary, OrderSummary
from src.policies.catalog import PolicyService


@dataclass
class FakeResponse:
    content: types.Content
    text: str | None = None

    @property
    def candidates(self):
        return [SimpleNamespace(content=self.content)]


class FakeModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append({**kwargs, "contents": list(kwargs["contents"])})
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeClient:
    def __init__(self, responses):
        self.models = FakeModels(responses)


def direct(text: str) -> FakeResponse:
    content = types.Content(role="model", parts=[types.Part.from_text(text=text)])
    return FakeResponse(content=content, text=text)


def tool_call(name: str, args: dict) -> FakeResponse:
    part = types.Part(
        function_call=types.FunctionCall(name=name, args=args),
        thought_signature=b"keep-this-signature",
    )
    return FakeResponse(content=types.Content(role="model", parts=[part]))


def multi_tool_call(*calls: tuple[str, dict, str]) -> FakeResponse:
    parts = [
        types.Part(
            function_call=types.FunctionCall(name=name, args=args, id=call_id),
            thought_signature=f"signature-{call_id}".encode(),
        )
        for name, args, call_id in calls
    ]
    return FakeResponse(content=types.Content(role="model", parts=parts))


def service_with(tmp_path: Path, *responses) -> tuple[AgentService, FakeClient]:
    client = FakeClient(responses)
    service = AgentService(
        db_path=tmp_path / "app.db",
        policy_service=PolicyService(Path("data/policies/policies.json")),
        model_client=client,
    )
    return service, client


def test_allowed_product_tool_is_validated_and_signature_content_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.agent import service as agent_module

    seen = {}

    def fake_search(db_path, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(agent_module, "search_products", fake_search)
    call_response = tool_call(
        "search_products", {"query": "violão", "limit": 5, "available_only": False}
    )
    agent, client = service_with(tmp_path, call_response, direct("Não encontrei opções disponíveis."))

    result = agent.ask("Quais violões estão disponíveis?")

    assert result.answer == "Não encontrei opções disponíveis."
    assert result.sources == ("Catálogo de produtos (SQLite)",)
    assert seen["query"] == "violão"
    assert seen["available_only"] is False
    first_config = client.models.calls[0]["config"]
    assert first_config.automatic_function_calling.disable is True
    # The exact model Content object (including the thought signature) is reused.
    assert client.models.calls[1]["contents"][-2] is call_response.content


def test_order_tool_uses_backend_identity_and_exposes_no_customer_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.agent import service as agent_module

    captured = {}
    order = OrderSummary(
        order_id="P-1",
        order_date="2026-01-02",
        status="em_transporte",
        total_cents=12500,
        payment_method="PIX",
        tracking_code="BR123",
        estimated_delivery="2026-01-07",
        items=(OrderItemSummary("Violão teste", 1),),
    )

    def fake_get_owned_order(db_path, order_id, identity):
        captured.update(order_id=order_id, identity=identity)
        return order

    monkeypatch.setattr(agent_module, "get_owned_order", fake_get_owned_order)
    agent, client = service_with(
        tmp_path,
        tool_call("get_owned_order", {"order_id": "P-1"}),
        direct("O pedido está em transporte."),
    )

    result = agent.ask("Onde está meu pedido P-1?")

    assert result.answer == "O pedido está em transporte."
    assert captured == {"order_id": "P-1", "identity": DemoIdentity(customer_id="3")}
    tool_result = client.models.calls[1]["contents"][-1].parts[0].function_response.response
    assert "customer" not in str(tool_result).lower()
    assert "phone" not in str(tool_result).lower()


def test_multiple_tool_calls_keep_response_order_ids_and_policy_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.agent import service as agent_module

    monkeypatch.setattr(agent_module, "search_products", lambda *args, **kwargs: [])
    combined = multi_tool_call(
        ("search_products", {"query": "violão"}, "product-call"),
        ("lookup_policies", {"query": "horário"}, "policy-call"),
    )
    agent, client = service_with(tmp_path, combined, direct("Consultei o catálogo e o horário da loja."))

    result = agent.ask("Quero um violão e o horário da loja.")

    tool_parts = client.models.calls[1]["contents"][-1].parts
    assert [part.function_response.id for part in tool_parts] == ["product-call", "policy-call"]
    assert [part.function_response.name for part in tool_parts] == ["search_products", "lookup_policies"]
    assert any("seção 2" in source and "página(s) 2" in source for source in result.sources)


def test_invalid_arguments_and_unknown_tools_are_never_executed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.agent import service as agent_module

    def should_not_run(*args, **kwargs):
        pytest.fail("invalid or unknown tool must not execute")

    monkeypatch.setattr(agent_module, "search_products", should_not_run)
    agent, client = service_with(
        tmp_path,
        tool_call("search_products", {"limit": 999}),
        tool_call("dump_customer_database", {}),
        direct("Posso ajudar com produtos ou políticas da loja."),
    )

    result = agent.ask("Preciso de ajuda com um produto.")

    assert result.answer == "Posso ajudar com produtos ou políticas da loja."
    assert len(client.models.calls) == 3
    invalid_response = client.models.calls[1]["contents"][-1].parts[0].function_response.response
    unknown_response = client.models.calls[2]["contents"][-1].parts[0].function_response.response
    assert invalid_response == {"error": "invalid_arguments"}
    assert unknown_response == {"error": "unknown_tool"}


def test_agent_caps_tool_rounds_and_returns_safe_fallback(tmp_path: Path) -> None:
    repeated_calls = [tool_call("lookup_policies", {"query": "horário"})] * 4
    agent, client = service_with(tmp_path, *repeated_calls)

    result = agent.ask("Qual é o horário?")

    assert len(client.models.calls) == 3
    assert result.status == "limit_reached"
    assert "limite" in result.answer.lower()


def test_exact_public_faq_uses_policy_cache_without_a_model_client(tmp_path: Path) -> None:
    policy_service = PolicyService(Path("data/policies/policies.json"))
    agent = AgentService(
        db_path=tmp_path / "app.db",
        policy_service=policy_service,
        model_client=None,
    )

    first = agent.ask("Qual é o horário da loja?")
    second = agent.ask("qual e o horario da loja")

    assert "Segunda a Sexta-feira" in first.answer
    assert first.sources == second.sources
    assert any("seção 2" in source and "página(s) 2" in source for source in first.sources)
    assert policy_service.cache_info().hits == 1
    assert policy_service.cache_info().misses == 1


def test_missing_key_sdk_failure_and_input_limit_fail_safely(tmp_path: Path) -> None:
    from src.agent.gemini_client import GeminiConfigurationError, create_gemini_client

    with pytest.raises(GeminiConfigurationError):
        create_gemini_client(None)

    agent, client = service_with(tmp_path, RuntimeError("secret-like raw SDK error"))
    failed = agent.ask("Olá")
    too_long = agent.ask("x" * 8001)

    assert failed.status == "error"
    assert "secret-like" not in failed.answer
    assert too_long.status == "invalid_input"
    assert len(client.models.calls) == 1
