# Third-party notices

StormNowcast depends on open-source Python packages listed in `pyproject.toml`,
including FastAPI, h5netcdf/h5py, NumPy, pandas, Plotly, Pydantic, PyProj, PyYAML,
Requests, scikit-image, SciPy, Shapely, Streamlit, Uvicorn, and xarray. Each package
retains its own copyright and license; consult the installed distribution metadata
for the exact version and license text.

The interface embeds the Source Code variable upright font asset as **Storm Console**.
Its provenance and license reference are documented in `assets/fonts/README.md`.

Map tiles and attribution are supplied by CARTO and OpenStreetMap contributors through
Plotly. Their terms and attribution requirements apply; the application preserves
visible attribution. Basemap availability is independent of the cached observation.

NOAA CPC CMORPH files are external scientific data, not bundled source code. The
application records the provider, product, official URL, timestamp, processing steps,
and checksum for each downloaded archive. MOSDAC and IMD products are not
redistributed by this repository.

