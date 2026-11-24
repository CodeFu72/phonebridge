# Changelog


## 0.1.0-alpha.2 — fixes from a read-only code review (2026-11-24)

Found by a read-only review (Gemini 4 Neon High), each checked against the code before fixing:
- Install: `python-cairo` was missing from the install steps, so some new machines crashed on first launch. It is now listed, and the installer checks for it with a clear message.
- Demo mode no longer crashes when Notifications or Sound is switched.
- Guided setup lists every paired phone (marking the ones already messaging-ready), so a new iPhone that hasn't turned on message access yet still shows up.
- A message with an unknown character-set label falls back to UTF-8 instead of stopping the Bluetooth connection.
- A send that never started (for example, Bluetooth dropped first) now says "Not sent", keeps your draft and doesn't lock the composer.
- A finished send can no longer be relabeled "uncertain" by an older status signal.
- The background sky timer runs only while the animated sky is actually showing. Idle wakeups went from about 80 to 4 every 5 seconds (better for laptop fans).
- Wording: the Settings button is named correctly in the hint, and old assistant names are gone from terminal prompts.
- Three new tests (90 total).

## Unreleased — public alpha prep (2026-11-23)

- README: "Tested on" section, demo screenshot (fictional data), credit to Kirk Fuson (EchoLine); text limit corrected to 2,000 bytes with Shift+Enter line breaks.
- How-To and testing notes no longer refer to a personal launcher menu.
- New notification ding, made from scratch for PhoneBridge (no outside audio).

## 0.1.0-alpha.1 — local candidate, 2026-10-20

- Add a GTK 4 text client with phone selection, inbox previews, manual single-recipient composition and exact send review.
- Add favorites, filtering, generic opt-in notifications and visible connection state.
- Serialize Bluetooth activity outside the UI thread; reuse the MAP session for send/receive.
- Keep message content in memory and write only explicitly saved favorites.
- Preserve transfer terminal receipts and block repeat sends until uncertain outcomes are acknowledged.
- Include diagnostic tools, a bounded permission-solicitation helper, a per-user installer and release/acceptance documentation.

Terminal receive and send were demonstrated by the initial user. GUI visual, phone, reconnect and updated receipt acceptance are still pending. No public release has been published.

### Connection guide update

The initial user reports the desktop app works. Add HOW-TO.md and a guided pairing/permissions/capability-check script exposed as phonebridge-setup, phonebridge --setup and Connect iPhone… in the app. No automatic test text is sent. Pairing settings and temporary advertisements clean up on ordinary exit. The installer follows an existing personal Omarchy group when present and otherwise adds a normal Apps entry. Clean first-time guided pairing is not yet hardware-verified.

### Aliases and audible notification update

- Add Edit name for local aliases used in People, favorites, headings and send review; recipient addresses remain visible and unchanged.
- Match plus/nonplus international phone presentations without inferring missing country codes.
- Replace the session-only alert checkbox with saved Notifications and Sound switches and Test ding.
- Include a quiet original synthesized ding; rate-limit playback, keep old history silent, and request suppression of the desktop daemon's own sound.
- Save names/preferences in owner-only files, independently of favorites. Text history remains in memory.

34 automated tests pass. Live visual and popup/audio acceptance for these new controls remains pending.

### Full text and history scrolling fix

- Fetch complete text bodies for the selected person via the Bluetooth Message API, without attachments; remove private temporary download files afterward.
- Distinguish full text, loading and unavailable previews, with a retry control rather than silent truncation.
- Wrap long text and URLs within the available bubble width and add internal padding.
- Stop emitting/redrawing chat on empty polls. Preserve rows during updates, follow new content only when already near the bottom, and add Jump to latest.

43 local tests pass. Actual full-body interoperability, message wrapping and scroll behavior require live desktop acceptance after this update. The private reference screenshot is not included in source or release artifacts.

### Status-bar mode and compact chat

- Add a standard StatusNotifierItem tray icon and DBusMenu with connection state, local unread counts, chat toggle, Settings and Quit.
- Keep the GTK/Bluetooth app alive while hidden; provide fallback to a normal window if the tray cannot register or its host disappears.
- Add saved Live in status bar and Compact floating window preferences, migrating existing notification settings.
- Simplify the two-column chat and move pairing, phone connection, notifications, sound and presentation controls into a Settings popup.
- Bring only this process's main window to the current Hyprland workspace in compact mode, using targeted runtime dispatches without editing compositor configuration. Workspace mode remains available.
- Quit blocks an in-flight send and otherwise waits for the worker to close its connection and temporary files before exit.

58 tests pass. Real tray registration/menu interaction, unread behavior while hidden, compact layout and workspace placement remain live acceptance steps.

### Emoji composer

- Add a local emoji picker with cursor insertion, selection replacement, and the existing 500-byte limit and send safeguards.

### 2026-10-21 — Conversation management

- Sort conversations by latest message, including favorites.
- Add confirmed local-only thread deletion with persistent hashed dismissal markers; keep iPhone messages, saved contacts and texts arriving during confirmation.

### Incoming-image investigation

- Add a separate fresh-message attachment probe with temporary bounded downloads and metadata-only output. Chat image display is not implemented or verified.

### Keyboard review and send

- Focus Send text as the review dialog default: Enter reviews, then Enter confirms; Escape returns to editing. Restore composer focus after an accepted send.

### 2026-11-03 — Spellcheck, links and synthwave look

- Spell-checked composer (GtkSourceView + libspelling): misspellings underlined, right-click suggestions; still one line, Enter to review, 500-character cap.
- Clickable links in messages, with Open and an on-demand Preview card (title, site, thumbnail; video pages get Watch ▶). Nothing is fetched until Preview is clicked.
- New look borrowed from Rinse: night sky with striped sun and neon grid, chrome Monoton logo, Orbitron pill buttons, glowing bubbles, selected/unread highlights. Fonts bundled (OFL).
- Settings → Animated sky. The grid drifts only while the window is focused; the static sky is cached.
- Images and video remain unavailable: the iPhone's Bluetooth message service returned text only in the attachment probe.

84 tests pass.

### 2026-11-03 — Compact window on Hyprland 0.56

- Hyprland 0.56 replaced classic dispatch syntax with Lua (`hl.dsp...`), so compact placement had been failing silently. Placement now sends Lua dispatches and falls back to the classic syntax on older Hyprland. Window targets are validated before translation.

88 tests pass.
