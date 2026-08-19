# Shams → X Chat bot

A proof of concept that listens for new posts from four configured NBA news
accounts—`@ShamsCharania`, `@ChrisBHaynes`, `@memgrizz`, and `@GrizzliesPR`—and
immediately sends the canonical post link into an encrypted
X group chat.

It uses X's filtered stream rather than polling. SQLite deduplication prevents
normal reconnects and restarts from posting the same link twice.

## What is implemented

- Creates a filtered-stream rule for the five configured accounts, excluding reposts.
- Receives new matching posts over one persistent connection.
- Sends the canonical `https://x.com/{username}/status/{id}` link.
- Defaults to dry-run logging, so setup cannot accidentally message a group.
- Persists delivered post IDs in `state/bot.sqlite3`.
- Does not backfill posts on startup or reconnect.
- Registers the bot's X Chat identity and stores its private blob with mode 600.
- Loads the group's current conversation key from encrypted X Chat history.

## Prerequisites

- Python 3.10+ (3.12 is recommended and used by the Dockerfile).
- An X developer Project/App with prepaid API credits.
- An app-only bearer token for filtered-stream reads.
- For live delivery, an OAuth 2.0 **user** token for the bot account with
  `dm.read`, `dm.write`, `tweet.read`, and `users.read`.
- An encrypted X Chat group that can add the bot account.

### Does this require a separate bot account?

It requires an X **user identity**, because X Chat messages use OAuth user
context and are signed by that user's registered Chat XDK keys. It does not
strictly require a new account: your own account can authorize the app and send
the messages during testing.

For ongoing use, create a dedicated X account, authorize the developer app while
logged into that account, and add it to the group. Mark it as automated in X
under **Settings → Your account → Automation** and connect it to the human
account that manages it. Everyone in the group should knowingly opt in to the
automated messages.

## 1. Install and test

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
cp .env.example .env
```

Put the app-only token in `X_BEARER_TOKEN`. Leave `CHAT_DRY_RUN=true`, then:

```bash
shams-bot
```

On first run the bot creates its stream rule and then logs future links without
sending any existing posts.

To deliberately recover recent matching posts (for debugging only), run:

```bash
shams-bot --recover-recent
```

This may send up to ten unrecorded posts to the configured chat, so do not use
it for normal restarts or reconnects.

## 2. Provision encrypted X Chat

Configure `X_ACCESS_TOKEN` with the bot account's OAuth user token, then perform
the one-time, rate-limited public-key registration:

```bash
shams-register-chat --confirm
```

Copy the three printed `CHAT_*` values into `.env`. Never commit the private
key. **Only after registration succeeds**, add the bot account to the target
X Chat group; the membership change creates a conversation-key event encrypted
for the bot.

Obtain the group's `g…` conversation ID and set:

```dotenv
CHAT_CONVERSATION_ID=g...
CHAT_DRY_RUN=false
```

Restart `shams-bot`. It will decrypt the group's latest conversation key,
connect to the post stream, and send new links.

If group membership changes later, restart the process so it loads the rotated
conversation key before sending again.

## Test the chat integration

First, verify encryption and group delivery without waiting for a public post:

```bash
shams-test-chat --immediate
```

Then test the complete filtered-stream-to-chat path. Stop `shams-bot` first
because pay-per-use projects allow one filtered-stream connection:

```bash
shams-test-chat
```

The end-to-end test temporarily watches `@AP`, waits up to 15 minutes for its
next original post or reply, sends that link to the configured group, and
removes its temporary stream rule afterward. Choose another active account or
change the timeout if needed:

```bash
shams-test-chat --account Reuters --timeout 1800
```

The immediate test costs one chat write. The end-to-end test normally consumes
one Post read and one chat write.

## Docker

After completing identity registration and filling the environment:

```bash
docker build -t shams-x-chat-bot .
docker run --env-file .env -v "$PWD/state:/data" shams-x-chat-bot
```

The SQLite database and the registration blob must live on persistent storage.

## Cost controls and behavior

The rule only matches the configured accounts' posts, so a stream event should
cost one Post read.
Each live link is one X Chat/DM write. The optional manual recent recovery
returns up to ten resources and can add small read charges. Configure a
spending limit in the X Developer Console.

Delivery is at-least-once around ambiguous network failures: the database is
marked only after the send call succeeds. That avoids silently dropping a post,
but an HTTP response lost after a successful send could produce one duplicate
on retry.

## PoC limitations

- Credentials and the raw private-key blob are environment/file secrets; use a
  secret manager and Juicebox-backed key recovery for production.
- The first 100 group events must contain a key event decryptable by the bot.
- The process should be supervised so it restarts after crashes.
- X does not publish separate public rate-limit/pricing rows for every new
  `/2/chat` endpoint; verify the live endpoint's classification in your
  Developer Console.
