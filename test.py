from exopy import Instrument, Star

star = Star("TOI178")
instrument = Instrument(name="ESPRESSO", version="19", drs_version="latest")

properties = star.fetch_properties()
star.search_observations()

print(star.available_instruments())
print(star.available_product_types(instrument=instrument))
print(star.observation_date_range(instrument=instrument))

observations = star.download_observations(
    instrument=instrument,
    product_type="S1D_A",
    start_date="2019-09-29",
    end_date="2019-09-30",
)

print(properties)
print(len(observations))
print(observations[0].data)
