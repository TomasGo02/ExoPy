# ExoPy

ExoPy es un envoltorio orientado a objetos alrededor del ecosistema DACE para
obtener, almacenar, transformar y preparar datos de observaciones de exoplanetas.

## Estructura del Proyecto

```text
exopy/
  audit/
    session.py       # sesiones de usuario y registro estructurado de eventos
  core/
    data.py          # envoltorio de arrays y transformaciones
    instrument.py    # selector de instrumento
    observation.py   # metadatos de observación y carga de FITS
    star.py          # objeto de objetivo expuesto al usuario
  pipeline/
    acquisition.py   # orquestación reproducible de búsqueda y descarga
    indexing.py      # índices de observaciones
    processing.py    # normalización de metadatos y controles de calidad
  ports/
    interfaces.py    # puertos abstractos para fuentes de datos y almacenamiento
  sources/
    dace.py          # frontera de integración con dace-query
  storage/
    cache.py         # gestión de productos descargados
    hdf5.py          # persistencia local en HDF5
  utils/
    filters.py       # utilidades pequeñas para filtros DACE
docs/
  architecture.md
examples/
  basic_usage.py
tests/
```

## Ejemplo

```python
from exopy import Instrument, Star

star = Star("TOI178")
instrument = Instrument(name="ESPRESSO", version="19", drs_version="latest")

properties = star.fetch_properties()
observations = star.search_observations(
    instrument=instrument,
    product_type="S1D_A",
    limit=1,
    download=True,
)

print(star.available_instruments())
print(star.available_product_types())
print(star.observation_date_range())
print(observations)
print(star.products)
```

## Desarrollo

```bash
python -m pip install -e ".[dev]"
pytest
```
