# MOSDAC INSAT manual files

## Requested official product

- **Provider:** Space Applications Centre (ISRO), via MOSDAC
- **Product:** `3RIMG_L1C_ASIA_MER`
- **DOI:** `10.19038/SAC/10/3RIMG_L1C_ASIA_MER`
- **Product page:** <https://mosdac.gov.in/doi/164/>
- **Official format document:** <https://www.mosdac.gov.in/docs/INSAT3D_Products.pdf>
- **Access policy:** <https://www.mosdac.gov.in/data-access-policy>
- **Login required:** Yes; the product page states that access is for researchers
  registered on MOSDAC.

## Exact user action for the synchronized event

1. Register or sign in at <https://mosdac.gov.in/>. Do not share credentials with
   StormNowcast.
2. Open **Data Access -> Order Data** in the MOSDAC portal.
3. Select INSAT-3DR, Imager, product `3RIMG_L1C_ASIA_MER`, and request
   **2023-07-09 00:00 through 05:30 UTC**, half-hourly, covering the Asian sector.
4. Download the provider-generated HDF5 files. The documented/current pattern is
   `3RIMG_09JUL2023_HHmm_L1C_ASIA_MER*.h5`; keep the exact version suffix supplied
   by MOSDAC.
5. Place the untouched files in this directory. Do not rename or edit them.

For each file, run (replace the input and timestamp in the output name):

```powershell
.\.venv\Scripts\python.exe scripts\ingest_official.py `
  --source mosdac-insat3dr-l1c `
  --input data\manual\mosdac_satellite\3RIMG_09JUL2023_0000_L1C_ASIA_MER_V01R00.h5 `
  --output data\processed\insat\3RIMG_09JUL2023_0000_L1C_ASIA_MER.nc `
  --min-lat 29 --max-lat 33 --min-lon 75 --max-lon 79 `
  --confirm-official-origin
```

The product-specific reader validates L1C Imager metadata, derives WGS84 coordinates
from the file-supplied Mercator projection, converts `IMG_TIR1` counts with the
file-supplied `IMG_TIR1_TEMP` lookup table, optionally decodes `IMG_WV` as water-vapour
**brightness temperature**, and writes checksum provenance. It never treats the WV
channel as a direct humidity observation.

This code path is tested against synthetic files that mirror the official published
schema. It remains **awaiting authorized real-file verification** until one of the
requested MOSDAC files is supplied and successfully inspected. The generic
`--source mosdac` path remains available for other explicitly mapped CF-compatible
official products.
