PERSISTENT_SERVICES := db traefik kibana elasticsearch-coordinating redis-master logstash adminer 
RESTART_ALWAYS_SERVICES := api web rpc-worker
PUSH_SERVICES := api web logstash theia-init theia-proxy theia-admin theia-xv6
BUILD_ALLWAYS := api web



CURRENT_DIR := $(shell basename $$(pwd) | tr '[:upper:]' '[:lower:]')
IMAGES := $(shell \
	ruby -ryaml -rjson -e 'puts JSON.pretty_generate(YAML.load(ARGF))' \
	docker-compose.yml | jq '.services | .[].image | select(.!=null)' -r \
	2> /dev/null \
)
BUILT_IMAGES := $(shell \
	docker image ls | \
	awk '{print $$1}' | \
	grep -P '^($(CURRENT_DIR)_|os3224-)' \
	2> /dev/null \
)
RUNNING_CONTAINERS := $(shell docker-compose ps -q)
API_IP := $(shell docker network inspect anubis_default | \
	jq '.[0].Containers | .[] | select(.Name == "anubis_api_1") | .IPv4Address' -r | \
	awk '{print substr($$0, 1, index($$0, "/")-1)}' \
	2> /dev/null \
)
VOLUMES := $(shell docker volume ls | awk '{if (match($$2, /^anubis_.*$$/)) {print $$2}}')


help:
	@echo 'For convenience'
	@echo
	@echo 'Available make targets:'
	@grep PHONY: Makefile | cut -d: -f2 | sed '1d;s/^/make/'

.PHONY: build        # Build all docker images
build:
	docker-compose build --parallel --pull $(BUILD_ALLWAYS)

.PHONY: push         # Push images to registry.digitalocean.com (requires vpn)
push:
	docker-compose build --parallel --pull $(PUSH_SERVICES)
	docker-compose push $(PUSH_SERVICES)

.PHONY: debug        # Start the cluster in debug mode
debug: build
	docker-compose up -d $(PERSISTENT_SERVICES)
	docker-compose up \
		-d --force-recreate \
		$(RESTART_ALWAYS_SERVICES)
	@echo 'Waiting a moment before running migrations'
	sleep 3
	@echo 'running migrations'
	make -C api migrations
	@echo 'seed: http://localhost/api/admin/seed/'
	@echo 'auth: http://localhost/api/admin/auth/token/jmc1283'
	@echo 'site: http://localhost/'

.PHONY: mindebug     # Start the minimal cluster in debug mode
mindebug: build
	docker-compose up -d traefik db redis-master logstash
	docker-compose up \
		-d --force-recreate \
		api web rpc-worker
	@echo 'Waiting a moment before running migrations'
	sleep 3
	@echo 'running migrations'
	make -C api migrations
	@echo 'seed: http://localhost/api/admin/seed/'
	@echo 'auth: http://localhost/api/admin/auth/token/jmc1283'
	@echo 'site: http://localhost/'


.PHONY: jupyter      # Start he jupyterhub container
jupyter:
	docker-compose up --force-recreate --build api-dev

.PHONY: deploy       # Start the cluster in production mode
deploy: check build restart

.PHONY: backup       # Backup database to file
backup:
	./scripts/backup.sh

.PHONY: restore      # Restore to most recent backup
restore:
	./scripts/restore.sh

yeetdb:
	docker-compose kill db
	docker-compose rm -f
	docker volume rm anubis_db_data
	docker-compose up -d --force-recreate db

.PHONY: cleandata    # yeet data
cleandata:
	docker-compose kill
	docker-compose rm -f
	if [ -n "${VOLUMES}" ]; then \
		docker volume rm $(VOLUMES); \
	fi

.PHONY: clean        # Clean up volumes, images and data
clean:
	docker-compose kill
	if [ -n "$(RUNNING_CONTAINERS)" ]; then \
		docker rm -f $(RUNNING_CONTAINERS); \
	fi
	if [ -n "$(IMAGES)" ]; then \
		docker rmi -f $(IMAGES); \
	fi
	if [ -n "$(BUILT_IMAGES)" ]; then \
		docker rmi -f $(BUILT_IMAGES); \
	fi
	if [ -n "${VOLUMES}" ]; then \
		docker volume rm $(VOLUMES); \
	fi
	docker system prune -f
