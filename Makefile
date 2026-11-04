IMAGE ?= emporio-musica:local
PORT ?= 8503
SECRETS_MOUNT := $(if $(wildcard .streamlit/secrets.toml),-v "$(CURDIR)/.streamlit/secrets.toml:/app/.streamlit/secrets.toml:ro",)

.PHONY: build run up restart stop down logs clean

build:
	docker build -t $(IMAGE) .

run:
	docker run --rm -it -p 127.0.0.1:$(PORT):8501 \
		$(SECRETS_MOUNT) \
		-e ADMIN_ACCESS_KEY -e DEMO_ACCESS_KEY -e GEMINI_API_KEY \
		-e GEMINI_MODEL -e DB_PATH \
		$(IMAGE)

up:
	@if ! docker image inspect $(IMAGE) >/dev/null 2>&1; then \
		echo "Imagem $(IMAGE) não encontrada; construindo..."; \
		$(MAKE) build; \
	fi
	@docker rm -f emporio-musica >/dev/null 2>&1 || true
	docker run -d --name emporio-musica -p 127.0.0.1:$(PORT):8501 \
		$(SECRETS_MOUNT) \
		-e ADMIN_ACCESS_KEY -e DEMO_ACCESS_KEY -e GEMINI_API_KEY \
		-e GEMINI_MODEL -e DB_PATH \
		$(IMAGE)

restart: stop up

stop:
	@docker rm -f emporio-musica 2>/dev/null || true

down: stop

logs:
	docker logs -f emporio-musica

clean:
	docker rm -f emporio-musica 2>/dev/null || true
	docker image rm $(IMAGE) 2>/dev/null || true
