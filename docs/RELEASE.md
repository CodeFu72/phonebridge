# Sharing plan

Current stage: local desktop alpha, not yet released. Proposed first release: 0.1.0-alpha.1. License: MIT for original code.

## GitHub application release

- [x] Source, license, dependency/install instructions and privacy/limitations documentation.
- [x] Local unit tests and capability probes.
- [x] Standalone GTK application and per-user installer.
- [x] Initial user reports the desktop app works.
- [x] Shareable HOW-TO.md and guided connection script implemented.
- [ ] Detailed desktop acceptance, send-receipt verification and reconnect tests.
- [ ] Clean first-time connection wizard test and a second phone/adapter.
- [ ] Record exact tested iPhone/iOS, BlueZ and adapter versions.
- [ ] Full-body reading decision and usability polish after the initial review.
- [ ] Test clean install/uninstall and another machine/phone configuration.
- [ ] Add a synthetic-data screenshot, release archive checksum and versioned release notes.
- [ ] Review tracked files and archive for message data, private paths, device addresses, credentials and personal screenshots.
- [ ] Choose public repository owner/name and publish only after user instruction.

The local source archive uses an explicit allowlist and excludes favorites, capability reports, Obsidian notes and private phone content. Do not upload the user's home directory or local app-data directory.

## Omarchy marketplace path

The current GTK client is a standalone app. Marketplace entries are shell plugins with a public GitHub repository and a valid manifest. A later companion could provide a bar launcher/status or unread indicator, with messaging kept in the app. Status IPC and a shell plugin have not been implemented; do not submit the app as if it already satisfies the plugin contract.

Before a plugin submission: implement the shell entry point, use a unique community plugin ID, validate with `omarchy plugin validate`, test against the current shell, review dependency installation and privacy, then prepare the public submission for user review.

References: [official publishing instructions](https://plugins.omarchy.org/publish.html), [shell plugin manual](https://omarchy.org/manual/shell-plugins/).

## Standard tray versus native shell plugin

The standalone app now implements a standard status notifier tray item, with local unread status and compact GTK chat. This uses the existing Omarchy tray; no separate shell plugin has been implemented or submitted. Test native tray registration, hidden reception, workspace movement, menu and graceful Quit before a public alpha. A marketplace-specific shell companion remains optional future work.
