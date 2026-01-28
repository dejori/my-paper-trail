# Setup Instructions

## Getting Started
1. Click "Use this template" to create your own repo
1. Add your Mendeley/Zotero credentials as secrets (see below)
1. The workflow runs daily and updates your reading list (or trigger manually from Actions tab)


## Setup

Configure one or both sources below. The script will use whichever credentials are present.


### Mendeley Setup

#### 1. Create a Mendeley app

1. Go to [Mendeley Developer Portal](https://dev.mendeley.com/myapps.html)
2. Click "Register a new app"
3. Fill in:
   - Application name: `paper-trail` (or anything)
   - Redirect URL: `https://localhost`
   - Check all the scopes you need (at minimum: `all`)
4. Note your **Client ID** and **Client Secret**

#### 2. Get your refresh token

Run this in your terminal (replace the values):

```bash
# Step 1: Open this URL in your browser
echo "https://api.mendeley.com/oauth/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=https://localhost&response_type=code&scope=all"

# Step 2: After authorizing, copy the 'code' from the redirect URL
# It looks like: https://localhost/?code=XXXXXX

# Step 3: Exchange code for tokens (run immediately, codes expire fast!)
curl -X POST https://api.mendeley.com/oauth/token \
  -d "grant_type=authorization_code" \
  -d "code=YOUR_CODE" \
  -d "redirect_uri=https://localhost" \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET"
```

Save the `refresh_token` from the response.

#### 3. Add Mendeley secrets to your repo

Go to your repo → Settings → Secrets and variables → Actions → New repository secret

Add these three secrets:
- `MENDELEY_CLIENT_ID` — Your client ID
- `MENDELEY_CLIENT_SECRET` — Your client secret
- `MENDELEY_REFRESH_TOKEN` — The refresh token from step 2


### Zotero Setup

#### 1. Create a Zotero API key

1. Go to [Zotero API Keys](https://www.zotero.org/settings/keys)
2. Click "Create new private key"
3. Give it a name (e.g., `my-paper-trail`)
4. Under "Personal Library", check **Allow library access**
5. Leave other permissions unchecked (read-only is sufficient)
6. Save and copy the API key

#### 2. Get your User ID

Your numeric user ID is shown on the same page: "Your userID for use in API calls is XXXXXXX"

#### 3. Add Zotero secrets to your repo

Add these two secrets:
- `ZOTERO_API_KEY` — The API key you created
- `ZOTERO_USER_ID` — Your numeric user ID


## Local Development

Requires Python 3.12+

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
pytest tests/ -v  # API tests skip without credentials
python sync.py
```

## License

MIT
