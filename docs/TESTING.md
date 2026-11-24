# Acceptance plan

## Already established

- The user's nearby paired iPhone advertises MAP and ANCS.
- A temporary ANCS solicitation exposed the missing message permission.
- Enabling the permission allowed a MAP session to open.
- A fresh incoming text appeared in the terminal receive test.
- The user confirmed an outgoing terminal-test text worked.
- The initial user reported that the installed GTK desktop app works. Individual detailed acceptance steps below were not separately confirmed.

Device model and exact iOS version have not been confirmed. We must not advertise a broader compatibility matrix from these observations.

## Local automated checks

The suite covers strict recipient validation, UTF-8 byte lengths, BlueZ `utf8` versus bMessage `UTF-8`, safe fresh-message selection, session cleanup, terminal receipt preservation, no inferred success from missing objects, uncertain-send acknowledgement, stable reconnect message keys, private favorites permissions and atomic preservation after write failures. Runtime syntax and GTK constructor-property checks also run locally.

The restricted agent environment has no usable display or Bluetooth bus and cannot open even a local Broadway listener. No screenshot, live GUI test or post-fix send-receipt success is claimed from those checks.

## Desktop acceptance — basic user smoke check reported successful; detailed checks pending

Use the installed app with the existing paired iPhone. Close terminal transport tests first so there is only one MAP client.

1. Open PhoneBridge from the launcher. Verify readable text, hover contrast and window resizing on the real display.
2. Select phone, Connect, inspect the current limited inbox previews, and receive a fresh test text.
3. Select a sender, check the address, favorite/unfavorite them, search, and enable Favorites only. Reopen the app: favorites should remain, local outgoing history should not.
4. Compose to one known recipient, inspect the exact review dialog, cancel once, then intentionally send. Confirm recipient receipt and the actual service on iPhone. Don't post private content.
5. Check accepted versus uncertain receipts. No repeated click should send twice; an uncertain send must require phone inspection/acknowledgement and never auto-retry.
6. Disconnect/reconnect. The UI must stay responsive, keep the draft on connection errors, and avoid duplicate incoming previews. Switching to a different paired phone clears the prior in-memory display.
7. Turn Notifications and Sound on, use Test ding, then receive a fresh test. Confirm one generic popup and one short ding, without message text. Turn Sound off: a fresh text should show a silent popup. Turn Notifications off: neither popup nor ding should occur. Reconnect: existing previews should remain silent. Reopen the app: switch choices should remain saved.
8. Disconnect or move the phone out of range; check error and reconnect controls. Check no message is submitted without review after reconnecting.
9. Quit: no receive/send worker should remain. Restart after a laptop and phone reboot and check permission persistence.

Before a public release, test another phone/iOS/adapter setup and document failures and recovery steps. Use synthetic demo data for release screenshots.

## New first-time connection guide — live test pending

The wizard has not yet been run from a clean pairing on another iPhone. Test that matching-code confirmation is explicit, unexpected devices are rejected, timeout/Cancel restores adapter settings, the agent and advertisement clean up, the permission step works, and only a capability check runs. Test the already-paired path without forgetting the working bond. Never send an automatic setup text.

The guide changes discoverability/pairability temporarily and restores them on ordinary exit/cancel. If the process is forcibly killed, finalizers cannot run; the bounded discoverability/advertisement timers still limit visibility, but users may need to restore Pairable manually. Powering Bluetooth on is explicitly approved and intentionally persists. The wizard temporarily requests the default BlueZ agent role; BlueZ cannot report the prior default agent, so it unregisters itself without claiming to restore a previous agent selection.

## Aliases and notification update — live visual/audio acceptance pending

Select a favorite, Edit name, save an alias, and confirm the name appears in the list/heading/review while the actual recipient remains visible. Clear an alias, unstar/restar a number, and reopen the app to verify persistence. Check +country-number and country-number presentations match without merging a number missing its country code. Confirm searches match both alias and actual address.

Local automated tests cover rename/remove/reload, independent favorites, owner-only files, notification defaults and persistence, initial-history/master-off/sound-off suppression, one ding per new-message batch, and missing/rate-limited audio players. Live popup suppression and audio output need checking on the desktop. No live sound is played by the automated checks.

## Full text and scrolling update — live check pending

1. Open the updated app and select a person with a text longer than 255 characters. Confirm Loading full text changes to the complete text, with line wrapping and paragraphs preserved. Compare privately against the iPhone.
2. Scroll up, wait through multiple four-second polls, and receive a new text. Confirm the viewport stays put. Empty polls should not replace rows. Jump to latest should explicitly return to the bottom.
3. Stay at the bottom and receive a new text; verify it follows naturally. Switch people and confirm the new person's latest text opens without making the old person's pending downloads take precedence.
4. Disable the phone connection while loading: confirm any failure retains an explicitly marked preview and a usable retry control on reconnect, without blocking the interface or resending anything.
5. Confirm old/incoming full-body downloads do not trigger extra notifications. Send a reviewed text while other bodies remain queued; it should take precedence after the in-progress transfer finishes.

Local tests cover long Unicode/multiline body parsing, incomplete/oversize rejection, structural-looking text, MIME plain-text decoding, private download cleanup with attachments disabled, no empty-poll redraw, and reading-position protection against queued scroll callbacks. These do not prove the phone's full-body behavior or a real rendered scroll layout.

## Status bar / compact chat — live acceptance pending

1. Finish any draft in the old app and exit it before starting this update. Confirm the new window is compact/floating on Omarchy and shows People left, chat right, and a Settings gear. Connect using Settings.
2. Confirm a PhoneBridge icon appears in the system tray (expand its drawer if needed). Hide with X; verify Bluetooth reception and optional notifications keep working. Receive a new text: the icon's badge and tooltip should show an unread count without private text.
3. Click the icon from another workspace: the compact chat should appear there. Reading the selected person's latest message clears only their local unread count. Initial history and full-body updates should not create unread increments.
4. Right-click the icon and exercise Open/Hide, Settings and Quit. Reopening from the application launcher must reach the existing single instance, not open another Bluetooth worker.
5. Turn Compact floating window off: the main window should tile normally. Turn Live in status bar off: closing should exit. Re-enable both and verify preferences survive a complete Quit/restart.
6. Quit during a pending send must wait for a result; hiding must not cancel the send. Ordinary Quit should wait for worker shutdown and temporary file cleanup. Nothing is automatically resent.
7. On a supported tray-host restart, a hidden app should show its fallback window and register again. Without any tray host it must never hide itself irretrievably.
8. Confirm no phone setup, bar layout, compositor config or login startup is silently changed. Runtime workspace operations may target only this process's main PhoneBridge window, never dialogs or other apps.

Local tests cover DBusMenu/SNI payload marshalling, correct bus-name registration, ARGB icon sizes, local unread accounting, settings migration, hide availability, pending-send quit protection, worker shutdown ordering and exact window-target dispatches. They do not replace a real desktop/tray test.

Emoji acceptance: insert at start/middle/end, replace selected text, try a nearly full 2,000-byte draft, and verify Review shows the exact emoji. Confirm the picker is disabled during pending or uncertain sends. Live GTK acceptance remains pending.

Conversation acceptance: receive a text from an older contact and verify it moves above newer/favorite contacts; verify Favorites-only retains recency order. Cancel Delete thread, then confirm it. Check iPhone messages remain. Reopen/reconnect and verify cleared history remains hidden; a new incoming text restores the thread without restoring old texts. Verify texts arriving during confirmation survive. Pending/uncertain sends must disable deletion. Live acceptance pending.

Keyboard acceptance: in the composer, Enter opens Review without sending. A second Enter submits once; Escape instead preserves the draft and returns focus. After an accepted send, type the next draft without clicking. Verify disconnected/invalid/pending/uncertain send gates still hold. Live keyboard acceptance pending.
