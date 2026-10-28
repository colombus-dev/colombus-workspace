# Colombus Workspace

Monorepo of submodules that make up the colombus platform:

- `colombus`: main app and API
- `annotation`: annotation app and API
- `mlprofiler`: internal ML profiling API, used by `colombus`, not public
- `colombus-flink`: standalone data pipeline and notebooks, run separately

## First time setup

### Dev

Run these commands locally :
```sh
git clone --recurse-submodules colombus-workspace
cd colombus-workspace
make env-init   # copies each submodule's .env.sample.dev to .env, skips files that already exist
# fill in the generated .env files with real secrets
make up
```

### Production

Run these commands on the prod host :
```sh
git clone --recurse-submodules colombus-workspace
cd colombus-workspace
make env-init ENV=prod   # copies each .env.sample.prod to .env, skips files that already exist
# fill in the generated .env files with production secrets
make up ENV=prod
```

## Everyday use

```sh
make up     # build and start all dev services
make logs   # follow logs across all services
make down   # stop everything
```

For prod, add `ENV=prod` to any command. To target specific apps instead of all of them, add `APPS="colombus annotation"` (any subset of `colombus`, `annotation`, `mlprofiler`).
