from __future__ import annotations

import time
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
        status = message.get("status", "ok")
        if status not in {"ok", "limit_reached"}:
            st.caption("A resposta ficou limitada pela configuração ou pelo resultado disponível.")


def _render_admin_metrics(policy_service) -> None:
    metrics = st.session_state.setdefault("session_metrics", _empty_metrics())
    cache_info = policy_service.cache_info()
    st.sidebar.subheader("Métricas desta sessão")
    st.sidebar.metric("Consultas", int(metrics["requests"] or 0))
    st.sidebar.metric("Erros / configuração", int(metrics["errors"] or 0))
    st.sidebar.metric("Última latência", f"{metrics['last_latency_ms']} ms" if metrics["last_latency_ms"] is not None else "—")
    st.sidebar.metric("Cache FAQ — hits", int(metrics["cache_hits"] or 0))
    st.sidebar.metric("Cache FAQ — misses", int(metrics["cache_misses"] or 0))
    st.sidebar.caption(f"Cache público em processo: {cache_info.currsize}/{cache_info.maxsize} entradas.")


def _clear_messages_for_profile_change() -> None:
    st.session_state["messages"] = []


def _render_chat() -> None:
    role = st.session_state.get("auth_role")
    if role not in {AppRole.ADMIN, AppRole.DEMO, AppRole.ADMIN.value, AppRole.DEMO.value}:
        clear_session(st.session_state)
        _render_login()
        return

    st.title("Empório da Música")
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

    try:
        database_path = runtime.ensure_database(runtime.get_database_path())
        policy_service = runtime.get_policy_service(str(POLICY_CATALOG))
    except Exception:
        st.error("Não foi possível preparar a base local. Verifique DB_PATH e os arquivos de demonstração.")
        return

    if can_view_metrics(role):
        _render_admin_metrics(policy_service)

    messages = st.session_state.setdefault("messages", [])
    for message in messages:
        _render_message(message)

    prompt = st.chat_input("Como posso ajudar?")
    if prompt:
        messages.append({"role": "user", "content": prompt})
        metrics = st.session_state.setdefault("session_metrics", _empty_metrics())
        cache_before = policy_service.cache_info()
        started = time.perf_counter()
        try:
            with st.spinner("Consultando..."):
                result = runtime.run_chat_turn(
                    db_path=database_path,
                    policy_service=policy_service,
                    message=prompt,
                    demo_profile=profile,
                    history=[
                        {"role": item["role"], "content": item["content"]}
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
