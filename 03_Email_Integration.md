# LifeLedger: Email Integration (Gmail API)

**Decided 2026-11-06:** the backend reads Gmail **directly through the Gmail API in Python**, with **read-only** OAuth. n8n is removed from the stack. Related: [01_Tech_Stack_Guide.md](01_Tech_Stack_Guide.md) · [02_Concepts_QA.md](02_Concepts_QA.md)

---

## 1. Options considered

| Option | How it works | Pros | Cons | Result |
|---|---|---|---|---|
| **A. Gmail API in Python** | Backend signs in once with Google OAuth and fetches new bank emails every 2 minutes | Read-only permission, no password stored, no extra service, testable, good resume value | One-time Google Cloud setup (~20 min) | ✅ **Chosen** |
| B. n8n Gmail trigger | n8n checks Gmail and forwards each email to a FastAPI webhook | No-code, quick start | Extra service to run and secure; it also just polls every minute | ❌ Dropped |
| C. IMAP + app password | Old mail protocol with a special Gmail password | Works with any provider | Stores a password with **full** mailbox access; Google discourages it | ❌ Fallback only, for non-Gmail providers |

**Why A:** it matches LifeLedger's rule of reading only, never changing anything. With the `gmail.readonly` scope, even a bug in our code cannot send, delete or change an email.

---

## 2. How it works

```
 Gmail                       trusted core                          sandbox
 ─────                       ────────────                          ───────
 Bank emails                 mail-fetcher (runs every 2 min,
 (filter adds   ──Gmail API──▶ started by a Temporal schedule)
  label                      1. list new emails with that label
  "LifeLedger")              2. skip ones already in Postgres
   read-only                 3. check the sender is really the bank
   OAuth                        (bank domain + DKIM/SPF pass)
                             4. save the email + PDFs ─────────────▶ parser container
                                to ./inbox/<email_id>/                (HTML → text, Docling,
                             5. record the email ID in Postgres      PDF unlock)
                                                                         │
                                   agent ◀── validated Pydantic JSON ◀───┘
```

### Step by step

1. The `mail-fetcher` loop runs every 2 minutes (see section 7).
2. The fetcher asks Gmail for messages matching `label:LifeLedger` that are newer than the last check.
3. It skips any Gmail message ID already stored in Postgres (idempotency).
4. It reads only the **headers** and checks:
   - the `From` domain is on the bank allowlist;
   - the `Authentication-Results` header shows **DKIM and SPF pass**.
   Failures are saved with status `unverified` and never reach the ledger.
5. It saves the raw email (HTML body and attachments) to `./inbox/<gmail_message_id>/`. It does **not** read the body itself.
6. The **parser sandbox** turns HTML into text, unlocks and reads PDFs with Docling, and returns Pydantic-validated JSON.
7. The agent categorises and matches it, as with SMS alerts.

---

## 3. One-time setup

### Google Cloud
1. Create a project in Google Cloud Console.
2. Enable the **Gmail API**.
3. Configure the **OAuth consent screen**: type External, add yourself as the only user.
4. Create an **OAuth client ID** of type **Desktop app**.
5. Download `credentials.json` into `secrets/` (git-ignored).

### First sign-in
6. Run the fetcher's `auth` command once. A browser opens; you click **Allow**.
7. Google returns a **refresh token**, saved to `secrets/token.json`. From then on the fetcher renews access by itself. No password is stored anywhere.

### Gmail
8. Create a Gmail filter: emails **from** your banks' alert addresses → apply label `LifeLedger`.
9. The fetcher only ever searches that label, so it never touches personal emails.

### Python libraries
- `google-api-python-client` (Gmail API calls)
- `google-auth-oauthlib` (first sign-in and token refresh)
- `pikepdf` (unlock password-protected PDFs, inside the sandbox)
- an HTML-to-text library such as `beautifulsoup4` (inside the sandbox)

---

## 4. Gotchas

| Gotcha | What happens | What we do |
|---|---|---|
| **7-day token expiry** | While the Google app is in "Testing" mode, refresh tokens for Gmail scopes expire after 7 days | For personal use, switch the app to "In production" without verification; you'll see an "unverified app" warning, which is fine since it's your own app. **Re-check Google's current rules at setup time** |
| **Can't mark emails as read** | Read-only scope can't add a "processed" label | Store each Gmail message ID in Postgres; this also prevents double counting |
| **Password-protected PDFs** | Most Indian bank and credit card statements are locked (often name, date of birth or PAN based) | Store the password pattern in `.env`; unlock with `pikepdf` **inside the sandbox** |
| **Untrusted HTML** | Emails can contain hidden text or prompt injection | HTML-to-text runs in the parser sandbox; the fetcher only reads headers |
| **Spoofed bank emails** | Phishing emails copy the bank's format | Bank domain allowlist + DKIM/SPF check; failures go to `unverified` |
| **The token is a mailbox key** | Whoever has `token.json` can read your mail | It lives only in the trusted `mail-fetcher` container, never in the parser, never in git |

---

## 5. Database tracking

A table such as `email_messages`:

| Column | Purpose |
|---|---|
| `gmail_message_id` (unique) | Prevents processing the same email twice |
| `received_at` | When Gmail received it |
| `from_address` | Sender |
| `auth_passed` | DKIM/SPF result |
| `status` | `fetched` → `parsed` → `saved`, or `unverified` / `failed` |
| `inbox_path` | Folder where the raw files were saved |
| `error` | Reason, if parsing failed |

---

## 6. Later options

- **Instant delivery (Phase 4):** Gmail push notifications through Google Cloud Pub/Sub with a **pull** subscription, so no public URL is needed. Checking every 2 minutes is enough for now, because UPI alerts also arrive instantly by SMS.
- **Google Calendar:** read renewal dates with the Calendar API (read-only scope), using the same OAuth setup. It replaces the Calendar part n8n used to cover.
- **Other providers:** Outlook/Hotmail through Microsoft Graph (same read-only OAuth idea); IMAP only as a last resort.

---

## 7. Changes to the stack

- **Removed:** n8n (and its Docker service and `n8n/` folder).
- **Added:** a `mail-fetcher` service (trusted core) that runs a simple "check, then sleep 2 minutes" loop.
- **Phase:** Gmail fetching starts in **Phase 1**, because many bank alerts arrive by email. The loop stays a loop in later phases too: polling is stateless and safe to repeat, so Temporal is kept for long waits only (decision D6 in the [implementation plan](docs/superpowers/plans/2026-11-06-lifeledger-00-overview.md)).
- **Table:** the plan stores emails, SMS and Telegram uploads in one `inbound_messages` table, which generalises the `email_messages` table in section 5 (decision D10).
