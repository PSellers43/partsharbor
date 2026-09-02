# PartsHarbor

**Prop 65, for the parts counter.**

PartsHarbor is a digital download business selling print-ready California Proposition 65 safe-harbor materials for people selling passenger and off-highway motor vehicle parts into California.

## Live site

The public marketing site is published with GitHub Pages:

**https://psellers43.github.io/partsharbor/**

| Page | URL |
|------|-----|
| Home | https://psellers43.github.io/partsharbor/ |
| Demo | https://psellers43.github.io/partsharbor/demo/ |
| Privacy Policy | https://psellers43.github.io/partsharbor/privacy/ |
| Terms of Service | https://psellers43.github.io/partsharbor/terms/ |
| Refund Policy | https://psellers43.github.io/partsharbor/refund/ |

## Repository layout

```
docs/                  Static site served by GitHub Pages
  index.html           Home — product, pricing, kit contents, demo section
  demo/                Demo video page (placeholder until MP4 is added)
  privacy/             Privacy policy
  terms/               Terms of service
  refund/              Refund policy
  css/styles.css       Site styles
  assets/previews/     Kit file preview images (SVG)
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

Open http://localhost:8080/ (paths match production except the `/partsharbor/` prefix).

## Product

- **Shop Kit** — $29 one-time digital download (zip of print-ready Prop 65 files)
- **Warning Updates** — optional $12/month file updates if OEHHA changes the published warning

Checkout is not live yet. The site uses a waitlist email CTA: patrick.ferrparts@gmail.com

## Demo video

Add `docs/assets/partsharbor-shop-kit-demo.mp4` and uncomment the `<video>` block in `docs/demo/index.html` to embed the walkthrough.

## Contact

Patrick Sellers — patrick.ferrparts@gmail.com

---

PartsHarbor — not legal advice. Uses OEHHA published safe-harbor methods.
