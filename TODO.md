# TODO - PR hardening for skybot

## Step 1: Fix merge conflicts
- [x] Clean `main.py` by removing all `<<<<<<< HEAD` / `=======` / `>>>>>>>` conflict markers.
- [x] Keep the FastAPI dashboard/WebSocket implementation (matches repo’s `tests/unit/test_smoke.py` expectations).

## Step 2: Fix dependencies
- [x] Clean `requirements.txt` by removing all conflict markers.
- [x] Pin FastAPI stack deps used by `main.py` and `tests`.


## Step 3: Verify tests locally
- [ ] Run `pip install -r requirements.txt`.
- [ ] Run `pytest -q`.

## Step 4: CI alignment
- [ ] Ensure `.github/workflows/trading-bot.yml` installs dependencies correctly.
- [ ] If needed, adjust test step to not require extra deps beyond requirements.

## Step 5: Commit + PR preparation
- [ ] Create branch `blackboxai/<name>`.
- [ ] Commit with message.
- [ ] Push branch.
- [ ] Open PR on GitHub.

