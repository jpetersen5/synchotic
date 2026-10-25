# Bring Your Own Credentials (BYOC)

Google caps how many people can sign in through Synchotic's own Google app, and
rclone's shared sign-in is being retired. So the way to download everything,
including the game rips and large chart packs Google blocks for anonymous
downloads, is to make your own small Google app and sign in through it. It takes
about ten minutes in a browser, once.

Synchotic writes these same steps to `BYOC_SETUP_INSTRUCTIONS.txt` in its data
folder when you pick BYOC, and opens that folder, which is where the file you
download in step 7 goes.

Each link below opens in whichever project is selected in the dropdown at the
top of the Cloud Console. After step 1, check that it says `synchotic-byoc`
whenever you open one. A banner about Cloud Hub or the dashboard shutting down
is about Google's home page, not these steps.

## 1. Make a project

[console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate)

- **Project name:** `synchotic-byoc`. Leave the location as it is.
- Click **Create**, then pick `synchotic-byoc` in the project dropdown. Google
  may add numbers to the end of the project ID; that is fine.

## 2. Turn on the Google Drive API

[console.cloud.google.com/apis/library/drive.googleapis.com](https://console.cloud.google.com/apis/library/drive.googleapis.com)
→ **Enable**.

## 3. Fill in the app info

[console.cloud.google.com/auth/overview](https://console.cloud.google.com/auth/overview)
→ **Get started**.

- **App name:** `Synchotic`. **User support email:** your own address.
- **Audience:** External.
- **Contact information:** your own address.
- Agree to the user data policy, then **Create**.

## 4. Add the Drive scope

[console.cloud.google.com/auth/scopes](https://console.cloud.google.com/auth/scopes)
→ **Add or remove scopes**, paste this into the filter, tick it, **Update**,
then **Save**:

```
https://www.googleapis.com/auth/drive.readonly
```

Google calls this a restricted scope and warns you. That is expected: the app
runs on your machine and nothing is sent anywhere.

## 5. Fill in the branding

[console.cloud.google.com/auth/branding](https://console.cloud.google.com/auth/branding)

Google will not publish the app until these are set:

| Field | Value |
|---|---|
| App name | `Synchotic` |
| User support email | your own address |
| App logo | leave empty |
| Application home page | `https://noahbaxter.dev/synchotic/` |
| Privacy policy link | `https://noahbaxter.dev/synchotic/privacy.html` |
| Terms of service link | leave empty |
| Authorized domains | `noahbaxter.dev`, only if it asks |
| Developer contact | your own address |

**Save.**

## 6. Publish it (do not skip)

[console.cloud.google.com/auth/audience](https://console.cloud.google.com/auth/audience)
→ **Publish app** → confirm. It must say **In production**.

> **Warning:** left in **Testing**, Google expires your sign-in every 7 days and
> Synchotic signs you out weekly.

Google then says *"Your app requires verification"* and asks you to submit it
for review. Ignore it. Verification is for apps with more than 100 users; an
unverified app in production works for you, and the only cost is a one-time
"Google hasn't verified this app" screen when you sign in.

## 7. Create the client and download it

[console.cloud.google.com/auth/clients/create](https://console.cloud.google.com/auth/clients/create)

- **Application type:** Desktop app. **Name:** leave the suggested one.
- **Create**, then click **Download JSON** right away. Google shows the client
  secret only once, at creation. If you close the dialog without downloading,
  delete the client and create a new one.

## 8. Install it

Rename the download to exactly `credentials.json` and put it in Synchotic's data
folder: **Settings > App > Open data** opens it, next to
`BYOC_SETUP_INSTRUCTIONS.txt`.

| Windows | macOS | Linux |
|---|---|---|
| `%LOCALAPPDATA%\Synchotic\Data` | `~/Library/Application Support/Synchotic` | `~/.local/share/synchotic` |

## 9. Turn it on

In Synchotic: **Settings > Account > Mode** → **Bring Your Own Credentials**.
Sign-in opens straight away; use the same Google account. On Google's "unverified
app" screen click **Advanced**, then **Go to Synchotic (unsafe)**.

## Troubleshooting

**Signed out about once a week.** The app is still in Testing. Redo step 6, then
sign in again.

**Google will not publish.** Something in step 5 is missing. Fill in what the
Branding page flags, save, and publish again.

**Synchotic says BYOC is not set up.** The file must be named exactly
`credentials.json` (not `credentials(1).json` or `client_secret_….json`) and sit
in the data folder.

<details>
<summary><strong>For developers: environment variables</strong></summary>

Instead of the file, set both of these to the client ID and secret from step 7.
When both are set they take precedence over `credentials.json`.

```
SYNCHOTIC_OAUTH_CLIENT_ID
SYNCHOTIC_OAUTH_CLIENT_SECRET
```

A source checkout keeps its data in `.dm-sync/` beside the checkout unless
`SYNCHOTIC_OS_DIRS=1`, or when run through the `synchotic` command.

</details>
