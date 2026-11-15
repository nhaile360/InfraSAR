# InfraSAR
NASA Space Apps project exploring reservoir shoreline change at Roseires with NISAR and Sentinel-2.

The static site opens at [index.html](index.html). Start at the 2026 inlet comparison and open **Long-term observations** to investigate reservoir surface area or rainfall.

The bundled long-term records include NASA POWER precipitation for the MERRA-2 grid cell near Roseires and NASA Terra MODIS monthly reservoir surface area. See the [analysis and provenance](roseires-trends/README.md), [explorer build instructions](roseires-visuals/README.md), and [shoreline processing pipeline](roseires-pipeline/README.md).

## Build and publish

Run the static build with Python 3.12. The build uses the checked-in scientific artifacts, and visitors only need a browser.

```sh
python -m pip install -r requirements-site.txt
python -m unittest discover -s roseires-trends -p 'test_*.py'
python scripts/build_site.py
```

The build writes `dist/index.html`, `dist/version.json`, and the derived MODIS CSV. The version file identifies the commit on GitHub Actions and Cloudflare Pages. Publish only `dist/`. When updating the checked-in standalone copies, copy `dist/index.html` to both `index.html` and `InfraSAR-Roseires.html`.

The [GitHub Actions workflow](.github/workflows/pages.yml) builds and browser-tests every push to `main`. Where the repository's plan supports Pages, choose **GitHub Actions** under **Settings → Pages**, then run **Build and deploy InfraSAR** from the Actions tab. Future pushes to `main` deploy automatically. The workflow checks the deployed commit and tests the public site in Chromium.

For a private-repository Cloudflare Pages deployment, connect the GitHub repository in the Cloudflare Pages dashboard, set **Production branch** to `main`, and use `dist` as the output directory. Use Python 3.12 and the build command below. Cloudflare will build future pushes to `main`.

```sh
python -m pip install -r requirements-site.txt && python scripts/build_site.py
```

The site build needs no Earthdata credentials. Browser smoke tests can also be run locally with Playwright and Chromium installed.

```sh
python -m pip install "playwright>=1.52,<2"
python -m playwright install chromium
python scripts/smoke_site.py dist/index.html
```
