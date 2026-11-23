# Publishing approved articles (optional)

Email delivery is unchanged and stays the default. A client can **also** have approved
articles pushed to their own channels by adding a `publishing` list to their brand YAML
(`content_factory/brands/<brand_id>.yaml`).

When the operator presses **Approve & send to client** in /admin:

1. The delivery email goes out exactly as before.
2. The article is sent to each enabled destination.
3. The result for each destination is saved on the article YAML under `publications.<id>`
   (status `draft` / `published` / `sent` / `failed`, plus link, error and attempt count).

A failure never blocks the email. Failed articles show a **Publish failed** badge in the
Content tab; open the article and press **Retry publish**. A destination that already
succeeded is never sent the same article twice.

## Secrets

Brand YAMLs are synced to GitHub, so **never put a token, password or webhook URL in them**.
Each destination names an *environment variable* instead (e.g. `token_env: GITHUB_TOKEN_ACME`);
set that variable in Railway → Variables.

## Destinations

### GitHub repo (static-site blogs: Hugo, Jekyll, Astro, Eleventy, Next.js…)

Commits one markdown file per article with YAML front matter
(`title`, `date`, `slug`, `draft`, `author`, `description`).

```yaml
publishing:
  - id: site
    type: github
    repo: acme/acme-site
    branch: main                          # optional, default main
    path: content/posts/{date}-{slug}.md  # optional; fields: {date} {slug} {year} {month}
    token_env: GITHUB_TOKEN_ACME
    mode: draft                           # draft → `draft: true`; publish → `draft: false`
    post_url: https://acme.com/blog/{slug}/   # optional; link shown in admin
```

Token: a **fine-grained personal access token** limited to the client's one repository with
**Contents: Read and write**. The client can create it and send it to you, or add the
operator's GitHub account as a collaborator. Existing files are never overwritten.

Set `path` to match the site generator, e.g. Astro `src/content/blog/{slug}.md`,
Jekyll `_posts/{date}-{slug}.md`, Hugo `content/posts/{slug}.md`.

### WordPress

```yaml
  - id: blog
    type: wordpress
    site_url: https://example.com
    username: jit
    secret_env: WP_APP_PASSWORD_JIT_PURU   # WordPress → Users → Profile → Application Passwords
    mode: draft
```

### Webhook (Zapier, Make, custom)

```yaml
  - id: zapier
    type: webhook
    url_env: PUBLISH_WEBHOOK_ACME
    secret_env: PUBLISH_WEBHOOK_SECRET_ACME   # optional; adds X-SaidBy-Signature: sha256=<hmac>
```

POSTs JSON: `event`, `brand_id`, `client_name`, `run_id`, `title`, `slot_type`,
`generated_at`, `mode`, `markdown`, `html`. If the response JSON has a `url`, it is
shown as the link in admin.

### Common options

- `enabled: false` turns a destination off without deleting it.
- `slot_types: [long_blog]` limits a destination to certain content types.
