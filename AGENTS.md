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
