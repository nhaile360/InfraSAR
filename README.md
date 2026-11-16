# InfraSAR

InfraSAR is a NASA Space Apps [Earth System Trend Detective](https://www.spaceappschallenge.org/2026/challenges/earth-system-trend-detective/) project about Roseires Reservoir, Sudan.

Open the [public GitHub Pages explorer](https://nhaile360.github.io/InfraSAR/). **2026 shoreline** compares the NISAR radar and Sentinel‑2 optical pilot scenes. **Timeline** shows ten verified provisional NISAR passes, including eight radar-only passes, alongside optical classifications and DAHITI reservoir heights. **Long-term observations** presents separate NASA POWER rainfall and NASA Terra MODIS reservoir-area analyses. The same viewer is available in the standalone index.html and InfraSAR-Roseires.html files.

- [Scientific report, source inventory, and claim audit](docs/SCIENTIFIC_REPORT.md)
- [Locked scientific input hashes](docs/scientific-inputs.sha256)
- [Shoreline processing](roseires-pipeline/README.md), [NISAR inventory](roseires-pipeline/NISAR_TIMELINE.md), and [trend analysis](roseires-trends/README.md)
- [Explorer controls and offline build](roseires-visuals/README.md)

## Build and publish

Use Python 3.12. The website builds from the checked-in scientific inputs without credentials. Original upstream downloads use provider authentication as described in the report.

```sh
python -m pip install -r requirements-site.txt
python scripts/verify_science.py
python -m unittest discover -s roseires-trends -p 'test_*.py'
python -m unittest discover -s roseires-pipeline -p 'test_*.py'
python scripts/build_site.py
python -m pip install "playwright>=1.52,<2"
python -m playwright install chromium
python scripts/smoke_site.py dist/index.html
```

The build generates index.html, version.json, the MODIS CSV, and scientific-inputs.sha256 in dist/. When updating the standalone copies, copy dist/index.html to both root HTML files.

The [GitHub Actions workflow](.github/workflows/pages.yml) validates the inputs and browser-tests the site before publishing dist/ to GitHub Pages on main. The live [version record](https://nhaile360.github.io/InfraSAR/version.json) gives the commit and SHA-256 hashes of the deployed assets. [Deployment runs](https://github.com/nhaile360/InfraSAR/actions/workflows/pages.yml) record the public-site test results.

Contains modified Copernicus Sentinel data 2026. The scientific report lists provider and licence credits for all other input sources.
