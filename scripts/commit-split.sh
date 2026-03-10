#!/bin/bash
# Split local changes into 4 commits by feature. Run from repo root.
set -e
cd "$(dirname "$0")/.."

echo "=== 1/4 Restructuring module ==="
git add \
  api/v1/endpoints/restructuring.py \
  api/v1/schemas/restructuring.py \
  apps/dsa-web/src/api/restructuring.ts \
  apps/dsa-web/src/pages/RestructuringPage.tsx \
  apps/dsa-web/src/types/restructuring.ts \
  src/services/restructuring_service.py \
  api/v1/router.py \
  apps/dsa-web/src/App.tsx \
  src/storage.py
git commit -m "feat: add restructuring analysis module (API, Web UI, storage)"

echo "=== 2/4 Run-all keep latest and prune history ==="
git add \
  api/v1/endpoints/analysis.py \
  api/v1/schemas/analysis.py \
  src/services/task_queue.py \
  apps/dsa-web/src/pages/HomePage.tsx \
  apps/dsa-web/src/api/analysis.ts \
  apps/dsa-web/src/types/analysis.ts
git commit -m "feat: run-all keep latest only and prune history for configured stocks"

echo "=== 3/4 WebUI reload ==="
git add webui.py
git commit -m "feat: add WEBUI_RELOAD for dev auto-restart"

echo "=== 4/4 Misc updates ==="
git add \
  .env.example \
  README.md \
  api/v1/endpoints/stocks.py \
  api/v1/schemas/stocks.py \
  apps/dsa-web/package-lock.json \
  apps/dsa-web/src/api/stocks.ts \
  apps/dsa-web/src/components/settings/SettingsField.tsx \
  apps/dsa-web/src/utils/constants.ts \
  apps/dsa-web/src/utils/systemConfigI18n.ts \
  apps/dsa-web/vite.config.ts \
  data_provider/akshare_fetcher.py \
  data_provider/base.py \
  docs/CHANGELOG.md \
  docs/full-guide.md \
  main.py \
  requirements.txt \
  src/agent/llm_adapter.py \
  src/analyzer.py \
  src/config.py \
  src/core/config_registry.py \
  src/search_service.py \
  docs/analysis-module-to-llm.md \
  scripts/test_announcement_fetch.py
git commit -m "chore: config, docs, and misc updates"

echo "Done. Run: git push origin main"
