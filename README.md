# Empório da Música — assistente demonstrativo

Aplicação local de atendimento com Streamlit, SQLite e Gemini (`google-genai`). O catálogo e os pedidos são snapshots CSV; não há integração de loja em tempo real. A UI inicia um banco reproduzível com catálogo do exercício e pedidos/clientes sintéticos em `data/demo/`. O seletor de perfil é uma simulação, não autenticação de cliente.

## Executar localmente

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Preencha `ADMIN_ACCESS_KEY` e `DEMO_ACCESS_KEY` com valores distintos e `GEMINI_API_KEY` no arquivo local de secrets ou forneça essas variáveis pelo ambiente. Não coloque chaves em chat, código, commits ou screenshots. `GEMINI_MODEL` aceita configuração; o padrão é `gemini-3.5-flash-lite`. Disponibilidade e quota desse identificador precisam ser verificadas ao configurar uma chave. `DB_PATH` seleciona o SQLite; por padrão é `work/app.db`. Sem `GEMINI_API_KEY`, apenas as perguntas exatas de FAQ pública respondem; demais consultas exibem configuração necessária.

```bash
python -m streamlit run app.py
```

O padrão é `work/app.db`: se esse banco já existe, ele é preservado e usado. Para iniciar explicitamente uma demo limpa, defina `DB_PATH=work/demo.db` antes de executar; a aplicação cria esse banco a partir de `data/demo/`.

Para ingerir os CSVs originais no banco local (não necessário para a demo), use `python scripts/ingest.py --source-dir CAMINHO --db-path work/app.db`. Esses dados ficam ignorados pelo Git; avalie minimização antes de compartilhar qualquer cópia. A inicialização concorrente de banco usa `fcntl` e destina-se a Linux/macOS.

## Arquitetura e operação

`src/data/` valida e ingere as seis tabelas para SQLite, com valores monetários em centavos e consultas parametrizadas. `src/policies/` disponibiliza seções do manual e cache limitado apenas para FAQs públicas reconhecidas. `src/agent/` usa um ciclo manual Gemini com ferramentas de leitura allowlist e limite de rodadas. Pedidos recebem identidade resolvida no backend; o modelo não recebe IDs de cliente nem registros brutos. O histórico de chat permanece somente na sessão.

As duas chaves de acesso independentes são `ADMIN_ACCESS_KEY` e `DEMO_ACCESS_KEY`; a primeira habilita métricas agregadas apenas da sessão. Em Streamlit Community Cloud, configure os mesmos valores em **App settings → Secrets** e mantenha `GEMINI_API_KEY`, `GEMINI_MODEL` e, se necessário, `DB_PATH` ali. O repositório público e a hospedagem são objetivo de entrega, mas esta execução só prepara os arquivos localmente: não cria repositório remoto nem publica aplicação.

## Testes e limitações

Rode `python -m pytest -q` e `python -m compileall -q app.py src scripts tests`. Testes do agente usam cliente falso para validar fluxo sem API; nenhum teste real Gemini foi executado. Latência e qualidade do modelo não foram medidas. Guardrails reduzem risco, mas não detectam toda prompt injection. Não há autenticação real de cliente, escrita/cancelamento de pedido, persistência de conversas, vetores/RAG semântico ou fontes em tempo real. O manual pode conter ambiguidades; a aplicação cita seções e não resolve contradições por conta própria.

## Exemplos

Os roteiros em [`examples/roteiros.md`](examples/roteiros.md) são exemplos esperados, não transcrições de chamadas reais Gemini. A FAQ de horário foi verificada no teste local determinístico, sem Gemini.

## Assistência de IA


