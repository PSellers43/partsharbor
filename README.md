# PartsHarbor

Print-ready California Prop 65 safe-harbor materials for motor-vehicle-parts sellers.

PartsHarbor is a digital download business selling print-ready California Proposition 65 safe-harbor materials for people selling passenger and off-highway motor vehicle parts into California.

## Live site

The public marketing site is published with GitHub Pages.

| Environment | URL |
|-------------|-----|
| Staging (GitHub Pages) | https://psellers43.github.io/partsharbor/ |
| Intended custom domain | https://partsharbor.biz (requires DNS configuration — not verified live from this repo) |

| Page | Path |
|------|------|
| Home | `/` |
| Demo | `/demo/` |
| Privacy Policy | `/privacy/` |
| Terms of Service | `/terms/` |
| Refund Policy | `/refund/` |

Custom domain is configured via `docs/CNAME` (`partsharbor.biz`). Point DNS A/CNAME records at GitHub Pages and enable the custom domain in repository Settings → Pages when ready.

## Repository layout

```
docs/                  Static site served by GitHub Pages
  CNAME                Custom domain (partsharbor.biz)
  index.html           Home — product, pricing, kit contents, demo section
  demo/                Demo walkthrough page (video placeholder until MP4 is added)
  privacy/             Privacy policy
  terms/               Terms of service
  refund/              Refund policy
  css/styles.css       Site styles
  assets/previews/     Kit file preview PNGs (counter sign, labels, notice, title card)
.github/workflows/     GitHub Pages deploy workflow
```

## GitHub Pages setup

Deployment runs automatically on push to `main` via `.github/workflows/pages.yml`.

After merging to `main`, enable GitHub Pages in the repository settings if not already active:

1. Go to **Settings → Pages**
2. Under **Build and deployment**, set **Source** to **GitHub Actions**

The workflow uploads the `docs/` folder and deploys to the project site URL above.

## Local preview

```bash
cd docs
python3 -m http.server 8080
```

Open http://localhost:8080/ (paths match production except the `/partsharbor/` prefix on GitHub Pages).

## Product

- **Shop Kit** — $29 one-time digital download (zip of print-ready Prop 65 files)
- **Warning Updates** — optional $12/month file updates if OEHHA changes the published warning

Checkout is not live yet. The site uses a waitlist email CTA: sales.partsharbor@gmail.com

## Demo video

Add `docs/assets/partsharbor-shop-kit-demo.mp4` and uncomment the `<video>` block in `docs/demo/index.html` to embed the walkthrough.

## Contact

sales.partsharbor@gmail.com

---

PartsHarbor — not legal advice. Uses OEHHA published safe-harbor methods.
