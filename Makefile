ENV ?= dev
APPS ?= colombus annotation mlprofiler

NETWORK_dev  := colombus-dev_network
NETWORK_prod := colombus-net
NETWORK      := $(NETWORK_$(ENV))

COMPOSE := docker compose -f docker-compose.$(ENV).yml

SERVICES_colombus   := colombus_ui colombus_app colombus_postgresql
SERVICES_annotation := annotate_app annotate_api annotate_redis
SERVICES_mlprofiler := mlprofiler_api vespucci_parser_api

SERVICES := $(foreach app,$(APPS),$(SERVICES_$(app)))
ifeq ($(ENV),prod)
SERVICES += caddy
endif

ENV_INIT_dev := submodules/colombus/.env:submodules/colombus/.env.sample.dev \
                submodules/annotation/.env:submodules/annotation/.env.sample.dev \
                submodules/mlprofiler/docker/.env:submodules/mlprofiler/docker/.env.sample

ENV_INIT_prod := submodules/colombus/.env:submodules/colombus/.env.sample.prod \
                 submodules/annotation/.env:submodules/annotation/.env.sample.prod \
                 submodules/mlprofiler/docker/.env:submodules/mlprofiler/docker/.env.sample \
                 .env:.env.sample.prod

.PHONY: up down logs ps env-init

up:
	docker network inspect $(NETWORK) >/dev/null 2>&1 || docker network create $(NETWORK)
ifeq ($(ENV),dev)
	$(COMPOSE) up -d --build $(SERVICES)
else
	$(COMPOSE) pull $(SERVICES)
	$(COMPOSE) up -d $(SERVICES)
endif

down:
	$(COMPOSE) down $(SERVICES)

logs:
	$(COMPOSE) logs -f $(SERVICES)

ps:
	$(COMPOSE) ps $(SERVICES)

env-init:
	@for pair in $(ENV_INIT_$(ENV)); do \
		dest=$${pair%%:*}; src=$${pair#*:}; \
		cp --update=none $$src $$dest; \
	done
