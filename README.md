# ExoPy

ExoPy is an object-oriented wrapper around the DACE ecosystem for fetching,
storing, transforming, and preparing exoplanet observation data.

## Project Shape

```text
exopy/
  clients/
    dace.py          # dace-query integration boundary
  storage/
    cache.py         # downloaded product management
    hdf5.py          # local HDF5 persistence
  utils/
    filters.py       # small DACE filter helpers
  data.py            # Data wrapper for arrays and transforms
  instrument.py      # Instrument selector
  observation.py     # Observation metadata and FITS loading
  star.py            # User-facing target object
docs/
  architecture.md
examples/
  basic_usage.py
tests/
```

## Example

```python
from exopy import Instrument, Star

star = Star("TOI178")
instrument = Instrument(name="ESPRESSO", version="19", drs_version="latest")

properties = star.fetch_properties()
observations = star.query_observations(
    instrument=instrument,
    file_type="S1D_A",
    limit=1,
    download=True,
)

print(star.available_instruments())
print(star.available_file_types())
print(star.observation_date_range())
print(observations)
print(star.products)
```

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```
