from __future__ import annotations

import time
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo
from pathlib import Path

import streamlit as st

from src.agent.service import AgentResult
from src.domain.session import AppRole, authenticate_session, can_view_metrics, clear_session, demo_profile_labels
from src.ui import runtime


PROJECT_ROOT = Path(__file__).resolve().parent
POLICY_CATALOG = PROJECT_ROOT / "data" / "policies" / "policies.json"


def _empty_metrics() -> dict[str, int | None]:
    return {
        "requests": 0,
        "errors": 0,
        "last_latency_ms": None,
        "cache_hits": 0,
        "cache_misses": 0,
    }


def _render_login() -> None:
    st.title("Empório da Música")
    st.subheader("Assistente de atendimento")
    keys = runtime.load_access_keys()
    if not runtime.access_keys_are_configured(keys):
        st.warning("O acesso ainda não está configurado. Configure as duas chaves de acesso no ambiente ou nos secrets.")
        return

    with st.form("login_form", clear_on_submit=True):
        entered_key = st.text_input("Chave de acesso", type="password")
        submitted = st.form_submit_button("Entrar")

    if submitted:
        role = authenticate_session(st.session_state, entered_key, keys)
        if role is None:
            st.error("Chave inválida ou configuração indisponível.")
            return
        st.session_state["messages"] = []
        st.session_state["session_metrics"] = _empty_metrics()
        st.rerun()


def _render_message(message: dict) -> None:
    with st.chat_message(message["role"]):
        st.markdown(message.get("content", ""), unsafe_allow_html=False)
        sources = message.get("sources") or ()
        if sources:
            with st.expander("Fontes consultadas"):
                for source in sources:
                    st.caption(source)
                for event in message.get("trace", ()):
                    if event.get("type") == "sql":
                        st.code(event["sql"], language="sql")
                        st.caption(f"Parâmetros: {event['parameters']}")
        status = message.get("status", "ok")
        if status not in {"ok", "limit_reached"}:
            st.caption("A resposta ficou limitada pela configuração ou pelo resultado disponível.")


def _render_admin_metrics(policy_service) -> None:
    metrics = st.session_state.setdefault("session_metrics", _empty_metrics())
    cache_info = policy_service.cache_info()
    st.sidebar.subheader("Métricas desta sessão")
    st.sidebar.metric("Consultas", int(metrics["requests"] or 0))
    st.sidebar.metric("Erros / configuração", int(metrics["errors"] or 0))
    st.sidebar.metric("Última latência", f"{metrics['last_latency_ms']} ms" if metrics["last_latency_ms"] is not None else "-")
    st.sidebar.metric("Cache FAQ - hits", int(metrics["cache_hits"] or 0))
    st.sidebar.metric("Cache FAQ - misses", int(metrics["cache_misses"] or 0))
    st.sidebar.caption(f"Cache público em processo: {cache_info.currsize}/{cache_info.maxsize} entradas.")


def _clear_messages_for_profile_change() -> None:
    st.session_state.pop("active_chat", None)


def _new_chat(profile: str, messages: list | None = None) -> str:
    chat_id = uuid4().hex
    st.session_state.setdefault("chats", {})[chat_id] = {
        "profile": profile, "title": "Nova conversa", "messages": list(messages or []),
        "created_at": datetime.now(ZoneInfo("America/Fortaleza")).strftime("%d/%m/%Y %H:%M"),
    }
    st.session_state["active_chat"] = chat_id
    return chat_id


def _render_details(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"thought_signature", "type"}:
                continue
            st.markdown(f"**{str(key).replace('_', ' ').capitalize()}**")
            _render_details(item)
    elif isinstance(value, (list, tuple)):
        if not value:
            st.caption("Nenhum")
        for index, item in enumerate(value, 1):
            if isinstance(item, (dict, list, tuple)):
                st.caption(f"Item {index}")
                _render_details(item)
            else:
                st.write(item)
    else:
        st.write(value if value is not None else "Não informado")


def _render_turn_trace(message: dict) -> None:
    labels = {
        "config": "Modelo e configurações", "model_request": "Envio ao modelo",
        "model_response": "Resposta do modelo", "tool_request": "Chamada de ferramenta",
        "tool_response": "Resposta da ferramenta", "sql": "Consulta SQL",
        "faq": "Consulta de política", "model_error": "Erro do modelo", "final": "Resposta final",
    }
    for event in message.get("trace", ()):
        kind = event.get("type", "evento")
        with st.expander(labels.get(kind, kind.replace("_", " ").capitalize())):
            if kind == "sql":
                st.code(event.get("sql", ""), language="sql")
                st.markdown("**Parâmetros**")
                _render_details(event.get("parameters", []))
            else:
                _render_details(event)


def _render_chat() -> None:
    role = st.session_state.get("auth_role")
    if role not in {AppRole.ADMIN, AppRole.DEMO, AppRole.ADMIN.value, AppRole.DEMO.value}:
        clear_session(st.session_state)
        _render_login()
        return

    header, header_action = st.columns([12, 1], vertical_alignment="center")
    header.title("Empório da Música")
    st.caption("Demonstração baseada em snapshot CSV local; os dados não são consultados em tempo real.")
    if not runtime.load_gemini_key():
        st.info("As perguntas frequentes de políticas estão disponíveis. Outras consultas precisam de GEMINI_API_KEY configurada.")

    with st.sidebar:
        st.markdown("#### Acesso")
        st.caption("Administrador" if can_view_metrics(role) else "Demonstração")
        st.markdown("#### Perfil de pedido")
        profile = st.selectbox(
            "Simular identidade de pedido",
            demo_profile_labels(),
            key="demo_profile",
            on_change=_clear_messages_for_profile_change,
            help="A seleção é uma simulação; não autentica um cliente real.",
            label_visibility="collapsed",
        )
        if st.button("Sair", use_container_width=True):
            clear_session(st.session_state)
            st.rerun()
        chats = st.session_state.setdefault("chats", {})
        if st.button("Nova conversa", use_container_width=True):
            _new_chat(profile)
            st.rerun()
        st.markdown("#### Conversas nesta sessão")
        for chat_id, chat in reversed(list(chats.items())):
            label = f"{chat['title']} - {chat.get('created_at', 'data indisponível')}"
            if chat["profile"] == profile and st.button(label, key=f"chat_{chat_id}", use_container_width=True):
                st.session_state["active_chat"] = chat_id
                st.rerun()

    try:
        database_path = runtime.ensure_database(runtime.get_database_path())
        policy_service = runtime.get_policy_service(str(POLICY_CATALOG))
    except Exception:
        st.error("Não foi possível preparar a base local. Verifique DB_PATH e os arquivos de demonstração.")
        return

    if can_view_metrics(role):
        _render_admin_metrics(policy_service)

    active_chat = st.session_state.get("active_chat")
    if active_chat not in chats or chats[active_chat]["profile"] != profile:
        active_chat = _new_chat(profile)
    chat = chats[active_chat]
    messages = chat["messages"]

    if can_view_metrics(role):
        with header_action.popover("❔", help="Ver detalhes dos turnos", use_container_width=True):
            st.subheader("Detalhes dos turnos")
            turns = [(i, message) for i, message in enumerate(messages) if message.get("role") == "assistant"]
            if turns:
                selected = st.selectbox("Selecionar turno", range(len(turns)), format_func=lambda n, turns=turns, messages=messages: f"{n + 1}. {messages[turns[n][0] - 1].get('content', '')[:45]}", key=f"details_turn_{active_chat}")
                index, selected_message = turns[selected]
                st.caption("Interações entre o assistente, o modelo e as ferramentas")
                _render_turn_trace(selected_message)
            else:
                st.caption("Envie uma mensagem para ver os detalhes.")
    if messages:
        with st.sidebar.expander("Voltar a um turno"):
            turns = [i for i, message in enumerate(messages) if message.get("role") == "assistant"]
            if turns:
                selected = st.selectbox("Selecionar turno", range(len(turns)), format_func=lambda n: f"{n + 1}. {messages[turns[n] - 1].get('content', '')[:45]}", key=f"turn_{active_chat}")
                if st.button("Continuar a partir deste turno", key=f"branch_{active_chat}"):
                    _new_chat(profile, messages[:turns[selected] + 1])
                    st.rerun()
    for message in messages:
        _render_message(message)

    prompt = st.chat_input("Como posso ajudar?")
    if prompt:
        if not messages:
            chat["title"] = prompt[:45]
        messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt, unsafe_allow_html=False)
        metrics = st.session_state.setdefault("session_metrics", _empty_metrics())
        cache_before = policy_service.cache_info()
        started = time.perf_counter()
        try:
            with st.chat_message("assistant"), st.spinner("Digitando..."):
                result = runtime.run_chat_turn(
                    db_path=database_path,
                    policy_service=policy_service,
                    message=prompt,
                    demo_profile=profile,
                    history=[
                        {"role": item["role"], "content": item["content"], "sources": item.get("sources", ())}
                        for item in messages[:-1]
                        if item.get("role") in {"user", "assistant"}
                    ],
                )
        except Exception:
            result = AgentResult(
                "Não consegui processar essa consulta agora. Tente novamente.",
                status="error",
            )
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        cache_after = policy_service.cache_info()
        metrics["requests"] = int(metrics["requests"] or 0) + 1
        metrics["errors"] = int(metrics["errors"] or 0) + int(result.status != "ok")
        metrics["last_latency_ms"] = elapsed_ms
        metrics["cache_hits"] = int(metrics["cache_hits"] or 0) + max(0, cache_after.hits - cache_before.hits)
        metrics["cache_misses"] = int(metrics["cache_misses"] or 0) + max(0, cache_after.misses - cache_before.misses)
        messages.append(
            {
                "role": "assistant",
                "content": result.answer,
                "sources": result.sources,
                "status": result.status,
                "trace": result.trace,
            }
        )
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Empório da Música", page_icon="🎸", layout="centered")
    if st.session_state.get("authenticated"):
        _render_chat()
    else:
        _render_login()


if __name__ == "__main__":
    main()
