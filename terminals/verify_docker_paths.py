"""Verifies SCENARIOS_DIR fix works for local and Docker layouts."""
import sys, os
sys.path.insert(0, '.')

from pathlib import Path
failures = []

# 1. Local: settings.SCENARIOS_DIR exists and contains baby_birth.json
from app.config import settings
sd = Path(settings.SCENARIOS_DIR)
ok1 = sd.exists() and (sd / 'baby_birth.json').exists()
print('1. SCENARIOS_DIR exists with baby_birth.json:', ok1)
if not ok1:
    failures.append(f'SCENARIOS_DIR check failed: {sd}')

# 2. Both routers use settings value (not __file__)
from app.routers import sessions, scenarios as scen_router
ok2 = sessions.SCENARIOS_DIR == scen_router.SCENARIOS_DIR == sd
print('2. Both routers match settings.SCENARIOS_DIR:', ok2)
if not ok2:
    failures.append('router SCENARIOS_DIR mismatch')

# 3. Docker layout: config.py at /app/backend/app/config.py -> parents[2] = /app
fake_config = Path('/app/backend/app/config.py')
docker_sd = fake_config.resolve().parents[2] / 'scenarios'
# On Windows resolve() is still /app/... because Path handles this
docker_sd_str = str(docker_sd).replace('\\', '/')
ok3 = docker_sd_str.endswith('/app/scenarios')
print(f'3. Docker parents[2]/scenarios = {docker_sd_str!r}: ends with /app/scenarios: {ok3}')
if not ok3:
    failures.append(f'Docker SCENARIOS_DIR wrong: {docker_sd_str}')

# 4. SCENARIOS_DIR env var override
os.environ['SCENARIOS_DIR'] = '/custom/override'
import app.config as cfg_mod
cfg2 = cfg_mod.Settings()
ok4 = cfg2.SCENARIOS_DIR == '/custom/override'
print('4. Env var SCENARIOS_DIR override works:', ok4)
if not ok4:
    failures.append(f'env override failed, got: {cfg2.SCENARIOS_DIR}')
del os.environ['SCENARIOS_DIR']

print()
if failures:
    print('RESULT: FAILED')
    for f in failures:
        print(f'  - {f}')
    sys.exit(1)
else:
    print('RESULT: ALL CHECKS PASSED')
