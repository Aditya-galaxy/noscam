# noscam.kronagent.dev

The public landing page: what NoScam is, downloads for every platform, and an optional
"get updates" email signup. Same setup as recap.kronagent.dev: a single Node server
(`server.js`, one dependency) plus static files in `public/`, on Cloud Run, scaling to zero.

- **Downloads** go through `/download/<platform>` → 302 to the latest GitHub release asset
  (stable names, so the page never needs a version bump). Each is counted in Firestore
  `downloads/<platform>`, at most once per IP per platform per hour.
- **Signups** go to Firestore database `noscam`, collection `signups`, one document per email
  (keyed by its SHA-256). Honeypot field, per-IP rate limit, and the same answer whether or not
  the address was already listed.
- **Privacy policy**: `docs/privacy.html` is the single source. `sync-privacy.py` copies it in
  and moves its inline styles to `privacy.css`, because the site's CSP allows no inline styles.
- The service runs as `noscam-site@kronagent.iam.gserviceaccount.com`, which can only reach the
  `noscam` database.

```bash
# local preview without touching Firestore
DRY_RUN=1 node site/server.js        # → http://localhost:8080
```

## First deploy (once)

```bash
# 1. A dedicated Firestore database
gcloud firestore databases create --project kronagent --database noscam --location us-central1

# 2. A service account that can only use that database
gcloud iam service-accounts create noscam-site --project kronagent --display-name "noscam.kronagent.dev"
gcloud projects add-iam-policy-binding kronagent \
  --member serviceAccount:noscam-site@kronagent.iam.gserviceaccount.com --role roles/datastore.user \
  --condition 'expression=resource.name=="projects/kronagent/databases/noscam",title=noscam-db-only'

# 3. Deploy (also how every later update ships)
python3 site/sync-privacy.py
gcloud run deploy noscam-site --project kronagent --region us-central1 --source site \
  --service-account noscam-site@kronagent.iam.gserviceaccount.com --allow-unauthenticated \
  --min-instances 0 --max-instances 3 --memory 256Mi --labels app=noscam

# 4. The domain (kronagent.dev is already verified from recap)
gcloud beta run domain-mappings create --project kronagent --region us-central1 \
  --service noscam-site --domain noscam.kronagent.dev
```

5. In **Spaceship → kronagent.dev → DNS**, add `CNAME  noscam  →  ghs.googlehosted.com.`
   Google issues the certificate on its own, usually within 15–60 minutes.

```bash
# signups as CSV (uses your gcloud login)
node site/export-signups.mjs > signups.csv
```
