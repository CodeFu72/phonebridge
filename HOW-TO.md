# How to connect your iPhone to PhoneBridge

This guide covers the setup used to get PhoneBridge working on an Omarchy laptop. The desktop app has worked on the initial user's setup; the new guided pairing script still needs a clean first-time test on another phone. Other iOS/adapter combinations may behave differently.

You do **not** need to leave a Mac running, enter an Apple password, jailbreak your phone, or connect to a cloud service. You do need your iPhone nearby with Bluetooth enabled.

## 1. Install PhoneBridge

From the extracted PhoneBridge source folder, open a terminal. On Omarchy:

```sh
omarchy pkg add bluez bluez-utils bluez-obex python-dbus python-gobject python-cairo gtk4
python scripts/install.py
```

Run the installer as your regular user, without `sudo`. The package command may ask for your system password. The installer adds the app and connection guide to your user account; it does not start messaging or enable a login service.

Other distributions need equivalent BlueZ/OBEX, Python, dbus-python, PyGObject and GTK4 packages. Only the initial Omarchy setup has been demonstrated; support for other distributions is not yet established.

## 2. Start the connection guide

Open PhoneBridge from your application launcher (on Omarchy: Super + Alt + Space). With the app disconnected, open the **Settings gear** at the top and click **Pair / setup…**. A terminal will open with the guided steps.

Alternatively, from a normal terminal:

```sh
phonebridge-setup
```

If your shell has not picked up the new command:

```sh
~/.local/bin/phonebridge-setup
```

From the source folder, the same guide is available as:

```sh
python connect_phone.py
```

Disconnect the app and close any other PhoneBridge diagnostic/transport tools before setup, so only one tool opens a messaging session at a time. **Do not disconnect your already working phone just to repeat setup.** Returning users normally just open the app and Connect.

The guide never reads message bodies or sends a test text. It will ask before pairing or turning Bluetooth on.

## 3. Select an existing phone, or pair a new one

The guide shows a numbered list. **Type the number before the item**, not the phone's name or your telephone number. For example:

```text
1. Example iPhone
2. Pair a new iPhone
Type the LIST NUMBER (0 cancels):
```

Choose `1` to use the already paired Example iPhone, or `2` to pair a new one. Lists vary by machine. Enter `0` to cancel.

For a new phone:

1. If more than one Bluetooth adapter exists, choose which adapter to use.
2. If Bluetooth is off, type `yes` when asked to turn it on.
3. On iPhone, open **Settings → Bluetooth** and leave the page visible.
4. The terminal shows your computer's actual Bluetooth name. Find that name under **Other Devices** on iPhone and tap it. It might be `omarchy`; it does not have to be your laptop model.
5. A six-digit code appears on both devices. Compare them carefully.
6. At the terminal confirmation question, type **yes** in full and press Enter. Then promptly tap **Pair** on iPhone. Keep both screens visible; the request can expire.
7. Approve additional service prompts only for the phone you are pairing. The wizard does not silently approve another device.

The pairing window lasts up to three minutes. The script restores the previous Discoverable, Pairable and discoverability-timeout settings when it finishes or is canceled. If you explicitly turned Bluetooth on, it remains on. The temporary pairing agent is unregistered afterward. Existing devices are never automatically forgotten, trusted or removed.

If pairing times out, let the guide exit and restart it. Confirm the new code; old codes are no longer valid. If iPhone shows a failed pairing with a Forget Device button, use it only for that failed attempt on the phone, then retry. Do not delete a working bond to diagnose a messaging permission problem.

## 4. Enable iPhone message access

After pairing, on iPhone:

1. Open **Settings → Bluetooth**.
2. Tap **ⓘ** beside your computer.
3. Enable **Show Message Notifications**, if present. Wording may vary.
4. Accept any related sharing prompt you intentionally requested.
5. Return to the guide and press Enter to check access.

You do not need contact syncing for this first version; there is no full address-book import.

### If Show Message Notifications is missing

This happened on the initial setup. Pairing succeeded and the phone advertised messaging, but the first messaging connection was denied.

The guide will offer a **temporary accessory signal**. Type `yes` to run it. While it says the signal is active:

1. Leave the computer's Bluetooth detail page on iPhone.
2. Reopen **ⓘ beside the same computer**.
3. Look again for **Show Message Notifications** and enable it.
4. Press Enter in the terminal to end the signal and continue.
5. Press Enter at the next check prompt after you have enabled the permission.

The signal expires after 90 seconds if you do nothing. It advertises PhoneBridge's interest in the iPhone notification service; it does not request an Apple password, read your notifications or send messages. Nearby devices can see the advertisement. The existing phone bond is preserved.

If the switch still does not appear, stop and record the phone model, iOS version, BlueZ version and adapter model for troubleshooting. Do not repeatedly unpair, reset network settings or disable security features. Different iOS versions may need further investigation.

## 5. Finish the access check

Success looks like:

```text
CONNECTED: messaging access verified. No text was read or sent.
```

This means the guide opened the phone's Bluetooth messaging interface and found the expected operations. It does **not** mean a text has been received or delivered.

Return to PhoneBridge, open **Settings**, click **Refresh**, select the phone, then **Connect**. The settings popup closes when connected. Keep the phone within Bluetooth range. The app stays responsive while Bluetooth work runs separately.

## 6. Receive a text

Ask someone to send a new text through their usual Messages app. It should appear in PhoneBridge's People list. Click the sender to load their complete text messages.

The current alpha discovers the latest 100 inbox previews, then downloads complete text bodies for the selected person. A loading label appears while text is being retrieved; a failed load stays explicitly marked **Preview only** with **Load full text** to retry. Attachments are not downloaded, and text downloads are limited to 2 MiB. This full-body path needs live acceptance on the phone after the update. It is not a complete import of Apple Messages. Other participants in a group are not identified reliably.

Long text and URLs wrap inside the chat. Scroll up to read older messages: new polls and texts should leave you where you are. When you are already near the bottom, new messages remain in view. Click **Jump to latest ↓** to return to the newest text.

To keep someone handy, select them and click **☆ Favorite**. Use **Favorites only** above the people list to filter. Favorite addresses and names are saved on this computer; text history is not saved by PhoneBridge.

To name a phone number, select it and click **Edit name** beside Favorite. Enter a familiar alias and click **Save name**. The name appears in People, favorites, the heading and send review; the real recipient address remains visible. To remove an alias, clear the name and save. Aliases survive reopening the app and unfavoriting a number. The app matches `+country-number` and `country-number` spellings but never guesses a missing country code or changes where a text is sent.

## 7. Send a text

1. Choose a sender, or click **New text**.
2. Check the **To** address. For a new person, enter their telephone number in international form, such as `+15551234567`, or their Apple-ID email. Do not enter just a contact name.
3. Type your text. Shift+Enter adds a line break. The limit is 2,000 UTF-8 bytes; emoji can use multiple bytes.
4. Click **Review text →**.
5. Read the exact recipient and text in the review window.
6. Click **Send text** only when both are correct. Keep editing cancels the send.

**One person per send.** Selecting a text that came from a group addresses its sender only. This version does not support group replies, attachments or calls.

The iPhone chooses iMessage or SMS. The app cannot reliably identify that service from the Bluetooth message type. Carrier charges depend on your plan.

**Accepted by iPhone** means the Bluetooth transfer completed, not that the recipient read or received it. Verify the first test on your iPhone and with the recipient.

If the app says the outcome is uncertain, **check Messages on your iPhone before sending again**. A transfer-receipt failure can occur after a text was sent. PhoneBridge never retries automatically. After inspecting the phone, click **I checked my iPhone** to clear the block and draft; compose again only if appropriate.

## 8. Everyday use

- Open PhoneBridge, open **Settings**, choose your paired phone and Connect.
- Turn **Notifications** on or off in **Settings**. Alerts are generic and omit message content.
- With Notifications on, turn **Sound** on for a short ding or off for silent popups. Click **Test ding** to check the selected computer audio output. Both choices are saved across app restarts. Notifications off disables both popup and ding. Old inbox previews loaded when connecting remain silent.
- If Test ding produces no sound, check volume/output. Sound needs `pw-play` (PipeWire), `paplay` (PulseAudio), or `canberra-gtk-play`; visual alerts can still work without them.
- The phone must remain nearby and connected. No Mac is required.
- Disconnect before running setup or another diagnostic messaging tool.
- If the phone moves out of range, check Bluetooth, then explicitly reconnect. There is no automatic reconnect yet.
- With **Live in status bar** enabled, X and **Hide to bar** hide the window while reception continues. Use the PhoneBridge tray icon or app launcher to reopen it. It may be behind the tray expansion arrow.
- To exit completely, choose **Settings → Quit PhoneBridge** or the tray menu’s Quit action. Quit waits for any Bluetooth work to finish and clears session text history. Favorites, aliases and settings remain. A pending send must finish before Quit.
- **Compact floating window** brings chat to the current Omarchy/Hyprland workspace. Turn it off in Settings to use a normal workspace window. The main chat keeps people on the left and messages/composer on the right.
- Tray badges are local unread counts. Initial inbox history is not counted. Viewing a person at the latest text clears their badge locally; it does not mark messages read on the phone.
- If no tray host is available, the app stays accessible as a normal window and X exits instead of hiding. PhoneBridge does not start automatically at login.
- Texts you send directly on iPhone may not appear here. Local outgoing history contains only sends made during this app session.

## Troubleshooting

| What you see | What to do |
| --- | --- |
| No phone in the list | Pair it with the guide, then Refresh. Headsets are not messaging phones. |
| Computer absent from iPhone Other Devices | Use Pair a new iPhone in the guide. It opens a bounded discoverable pairing window and shows the actual computer name. |
| Pairing unsuccessful | Confirm matching codes on both screens before timeout. Use `yes`, not a device name. |
| `OBEX Connect failed with 0x43` | Messaging permission was denied. Check the switch; use the temporary accessory signal if it is missing. |
| Window disappeared after X | Look for PhoneBridge in the system tray, expand the tray arrow, or launch PhoneBridge again. It is still receiving while hidden. Use Settings → Quit to exit. |
| Connection refused or another MAP client is active | Disconnect the app/close diagnostic clients. A competing computer Bluetooth connection may need to be disconnected. Retry once after resolving that conflict. |
| Permission to the system bus is denied | Run the guide in your ordinary logged-in desktop terminal as your user, not in a restricted agent shell or as sudo. |
| Send outcome uncertain / transfer object disappeared | Inspect the iPhone before composing again. Never assume the send failed solely because the receipt vanished. |
| Pair / setup button is disabled | Disconnect the app first and wait for any pending send. Setup and live messaging should not compete. |

## Before reporting a problem or sharing screenshots

Use `python app.py --demo` for a safe fictional screenshot. Do not post real phone numbers, contact lists, message text, pairing codes, favorites files or raw Bluetooth captures. Report the error name and the step where it occurred, plus nonsecret software/hardware versions.

See [README](README.md), [acceptance plan](docs/TESTING.md) and [release checklist](docs/RELEASE.md). PhoneBridge is experimental and unaffiliated with Apple or Omarchy. The basic desktop has been reported working on the initial user's setup; detailed acceptance and clean first-time wizard setup on other hardware remain release work.

### Emoji in your texts

Click **😊** beside the message box to choose a heart, smile or reaction. It inserts at the cursor or replaces selected text. Emoji count toward the 2,000 UTF-8 byte limit; shorten the draft if insertion would exceed it. Use **Review →** to send as usual.

### Conversation order and deletion

People and Favorites show conversations with the newest message first; contacts without messages follow alphabetically. Select a conversation and click **Delete thread** to clear its current history from PhoneBridge after confirmation. Your iPhone messages, aliases and favorites remain. Cleared favorites are hidden until a new text arrives. New messages restore the conversation at the top. Messages arriving while the confirmation is open are kept. Deletion is disabled during pending or uncertain sends.

Deletion markers persist as hashes of message identities and contact keys in the private `cleared.json` file beside your local settings; message bodies are not saved. These hashes are not encryption. Removing that file allows old iPhone inbox entries to reappear on reconnect. There is no in-app undo.

### Experimental incoming-photo capability check

This is a diagnostic, not image support in the chat UI. Disconnect PhoneBridge first, then run `python /path/to/phonebridge/attachment_test.py`. Choose the iPhone list number. Wait for Ready, then have someone send one new harmless photo. Type CHECK only when that new message was the test photo. The first fresh message is downloaded with attachments requested; older inbox content is ignored. The test prints only byte counts, image-format detection and a generic result, not message text or attachment filenames. Paste only the safe summary when reporting results.

The probe uses a private temporary directory, cancels oversized downloads at 12 MiB, and removes the temporary file on ordinary exit. It does not send, delete, fetch external links or save an image library. A detected image signature is evidence of delivered image bytes, not a verified display/decoder result. No detected image is inconclusive: repeat separately with iMessage and SMS/MMS photos if needed. Connect PhoneBridge again after the test exits.

### Keyboard sending

With the cursor in the message box, press **Enter** to review the exact recipient and draft. Press **Enter again** in the review window to send once. **Escape** returns to editing. After an accepted send, focus returns to the message box. Invalid drafts, disconnected state, pending sends and uncertain outcomes keep their existing safeguards.
