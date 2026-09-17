# PartsHarbor

Print-ready California Prop 65 safe-harbor materials for motor-vehicle-parts sellers.

PartsHarbor is a digital download business selling print-ready California Proposition 65 safe-harbor materials for people selling passenger and off-highway motor vehicle parts into California.

## Live site

The public marketing site will be **https://partsharbor.biz** (custom domain via `docs/CNAME`). DNS is not live yet; until it is, GitHub Pages serves the site at the project URL below as staging.

| Page | Public URL (when DNS is live) | Staging (GitHub Pages) |
|------|-------------------------------|-------------------------|
| Home | https://partsharbor.biz/ | https://psellers43.github.io/partsharbor/ |
| Demo | https://partsharbor.biz/demo/ | https://psellers43.github.io/partsharbor/demo/ |
| Privacy Policy | https://partsharbor.biz/privacy/ | https://psellers43.github.io/partsharbor/privacy/ |
| Terms of Service | https://partsharbor.biz/terms/ | https://psellers43.github.io/partsharbor/terms/ |
| Refund Policy | https://partsharbor.biz/refund/ | https://psellers43.github.io/partsharbor/refund/ |

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
3. When DNS is ready, point **partsharbor.biz** at GitHub Pages (the deploy artifact includes `docs/CNAME`). Until then, use the staging URL in the table above.

The workflow uploads the `docs/` folder (including `docs/CNAME` for the custom domain) and deploys to GitHub Pages.

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

Patrick Sellers — sales.partsharbor@gmail.com

---

PartsHarbor — not legal advice. Uses OEHHA published safe-harbor methods.
