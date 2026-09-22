# Fork working agreements

- This fork is maintained at `https://github.com/N0tANTi/jev-chat-jarvis`.
- The user authorized committing and pushing the session-safety fixes to this fork.
  This supersedes the upstream CLAUDE.md no-commit instruction for this work.
- Use the current ASCII checkout path; the upstream H: drive path is author-specific.
- Never auto-send messages, operate payments, hook chat apps, or read their databases.
- Never commit API keys, .env files, signing keys, chat history or new APK binaries.
  Trial APKs belong in ignored local build output or CI artifacts (14-day retention).
- Debug installs use `com.jev.probe.trial`, separate from the upstream app.
- Project state: `CURRENT_STATE.md`; remaining work: `ROADMAP.md`;
  trial procedure: `docs/runbooks/android-trial.md`;
  history: `docs/history/2026-09-22-session-safety.md`.
- Validate with `bash gradlew testDebugUnitTest assembleDebug lintDebug` on JDK 17
  with Android SDK 35, or the Android trial workflow. Device validation is separate.

## Desktop trial

- Desktop code lives in `desktop/`, on `codex/desktop-mineru-trial`, in this same fork.
  The user requested desktop implementation and GitHub synchronization applies here.
- The user explicitly authorized loading existing local `.env` credentials, including
  MinerU, DeepSeek and TypeSafe. This supersedes upstream's no-key-file restriction
  for ignored local configuration only. Do not commit those files or their contents.
- Startup must not capture or call APIs. Only the user-selected crop goes to MinerU.
  Manual generation requires review; explicitly enabled automatic mode may submit OCR
  text to DeepSeek / TypeSafe, but must not persist unreviewed OCR into friend memory.
  No real chat content in test fixtures. No filling, sending or database access.
- The user requested independent adaptation for current Weixin without Plus. Opt-in
  foreground capture is allowed: require a selected message crop and title guard,
  discard stale results, stop on title/window changes; default off and never auto-resume
  after restart. Do not claim visual title matching provides stable contact identity.
- Desktop validation: `python -m unittest discover -s desktop/tests -v`.
  Live smoke: `python -m desktop.smoke --env-file <local path>` uses synthetic data only.
- Desktop runbook: `desktop/README.md`; history: `docs/history/2026-09-22-desktop-trial.md`.
- User requested persona + per-friend history/tag learning. Explicitly saved profiles and
  opt-in reviewed chat learning persist in `%LOCALAPPDATA%/JevDesktop/profiles.json`.
  Imported history/profile context may be sent to DeepSeek/TypeSafe when the user runs
  analysis/generation. Automated capture is a separate, per-session explicit action.
- Keep confirmed user facts separate from evidence-backed model hypotheses. Contact
  identity is an explicit local UUID; never auto-merge contacts by display name.
- Current wxauto diagnostics are in `docs/runbooks/wxauto-diagnostics.md`.
