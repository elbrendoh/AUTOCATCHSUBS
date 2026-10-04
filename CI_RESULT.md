# Windows JR build verification

Status: PASSED, unsigned candidate. Verified October 3, 2026 (America/Lima).

Build: https://github.com/elbrendoh/AUTOCATCHSUBS/actions/runs/37172342244

Compiled commit: `0c9bf119eef6fc117c00416d75f4ca0b12634c18`

Installer: `AUTOCATCHSUBSJR-Setup.exe`, 107575545 bytes.

SHA256: `FA829C0FB5286C535E831177AEEB950A15D54539C0197039E87A57D421C247C2`

Passed on a disposable Windows runner:

- Public Python/JavaScript sources and interface reconstruction.
- Eleven synthetic regression tests: Text+ identity filtering, compressed metadata, read-only project access, incomplete scans/cache preservation, template selection and inactive JR HTTP mutation rejection.
- Rust/Tauri client and frozen Python backend builds with no private activation/signing credentials.
- Package hash verification; inactive native JR verifier returns 23 as expected.
- Compressed Text+ decoding, Tcl/Tk, backend startup and synthetic FFmpeg audio conversion.
- Installer compilation, installation into a path with spaces, offline runtime check, Lua menu registration and removal during uninstall.

Production license activations consumed: 0. Installed plugins on the maintainer's PC were not modified.

The executable/library inventory contains 76 valid vendor signatures and 6 unsigned PE files: our two executables, upstream FFmpeg and three Python extensions (cffi, backports.zstd, cryptography). The installer is also unsigned. Third-party files must not be signed using a project identity without the relevant authorization/policy; resolve their signing coverage with SignPath/upstream before production distribution.

This is not a signed production release. Smart App Control and a real Resolve timeline were not tested by this workflow. Passing these checks does not establish that Windows will permit the candidate on the previously blocked PC.

Build artifacts/reports are retained on GitHub for 3 days. Re-run the workflow to regenerate artifacts. Builds contain public configuration only; never upload the private vault, activation codes or Cloudflare signing/Admin secrets.
