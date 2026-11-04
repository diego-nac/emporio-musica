# Empório da Música

Aplicação de atendimento demonstrativa com Streamlit, SQLite e Google Gemini. O catálogo é carregado dos CSVs locais e os pedidos usam dados demonstrativos.

## Configuração

Configure `ADMIN_ACCESS_KEY`, `DEMO_ACCESS_KEY`, `GEMINI_API_KEY` e `GEMINI_MODEL` em `.streamlit/secrets.toml`. As duas chaves de acesso devem ser diferentes.

Exemplo de arquivo local, substituindo os valores pelos seus:

```toml
ADMIN_ACCESS_KEY = "uma-chave-de-administrador"
DEMO_ACCESS_KEY = "uma-chave-de-demonstracao-diferente"
GEMINI_API_KEY = "sua-chave-google"
GEMINI_MODEL = "gemini-3.5-flash-lite"
```

O modelo é configurável e precisa estar disponível na conta Google com suporte a chamadas de ferramentas. O arquivo de secrets é local e não deve ser enviado ao repositório.

## Executar com Docker

```bash
make build
make up
```

Acesse http://localhost:8503. Use `make restart` para reiniciar e `make down` para parar.

## Executar localmente

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

O banco de demonstração é gerado a partir de `data/demo/` na primeira execução. O histórico das conversas permanece apenas durante a sessão. O sistema consulta dados e orienta, sem executar compras, cancelamentos ou reembolsos.

Para importar outros CSVs compatíveis, consulte as opções de `python scripts/ingest.py --help`. O caminho do banco pode ser configurado por `DB_PATH`.

## Decisões técnicas

- **Interface:** Streamlit reduz a configuração necessária para experimentar o chat em Python.
- **Modelo:** Google Gemini por API, com identificador configurável, interpreta a conversa e solicita ferramentas. A disponibilidade e a cota dependem da conta utilizada.
- **Agente:** um único serviço executa chamadas de ferramentas de leitura com limite de rodadas. O modelo não executa SQL arbitrário. O prompt estabelece persona, limites de atuação e necessidade de fundamentar informações nas ferramentas.
- **Dados:** SQLite armazena os dados importados dos CSVs, com consultas parametrizadas. O catálogo e os pedidos são snapshots, sem atualização em tempo real.
- **Políticas:** recuperação local por regras e correspondência normalizada, com cache limitado para perguntas frequentes. Não utiliza embeddings nem busca vetorial. As referências apontam para a transcrição do manual.
- **Sessão:** histórico e detalhes de ferramentas ficam na sessão do Streamlit e são descartados ao sair ou reiniciar. As duas chaves controlam o acesso ao protótipo. O perfil de cliente é simulado, não uma autenticação real.

## Limitações e suposições

- Os preços, estoques e pedidos demonstrativos não representam uma integração com a operação da loja. Alterações nos CSVs exigem nova ingestão.
- A busca por políticas é lexical e pode não identificar todas as formas de uma pergunta. Há respostas que dependem do modelo e podem exigir revisão.
- Em testes conversacionais, algumas buscas atingiram o limite de ferramentas e houve respostas fora do escopo ou interpretações indevidas de políticas ambíguas. O prompt foi ajustado depois, mas uma nova rodada completa ainda é necessária.
- O manual informa condições de frete para valores abaixo e acima de R$ 500, sem definir explicitamente o valor exato. Essa situação precisa de esclarecimento humano.
- O atendimento não finaliza compras, registra solicitações nem altera pedidos. A autenticação de clientes e a privacidade de produção exigiriam uma solução própria.
- Com mais tempo: melhorar o tratamento de chamadas repetidas, avaliar as respostas em conversas completas, adicionar observabilidade e autenticação de clientes, e validar a atualização dos dados com a operação.

## Exemplos

Há quatro trechos de conversas executadas com dados demonstrativos em [examples](examples/), cobrindo promoções, trocas, privacidade e pagamento. Os exemplos são snapshots de uma execução e seus valores podem mudar com os dados.

## Testes

```bash
python -m pytest -q
```
