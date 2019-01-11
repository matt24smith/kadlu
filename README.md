# Welcome to the Ocean Soundscape Toolbox python package!

This package, also know as **PyOST**, is currently under development, but will eventually 
contain a bunch of tools useful for modeling the underwater ocean 
soundscapes, for example:

 * Automated retrieval of relevant environmental data, including static 
   data such as bathymetry and seabed properties, and dynamic data such 
   as water temperature, salinity, and wave height.

 * Derivation of underwater acoustic properties (such as sound speed) from 
   the environmental data and conversion into format suitable for sound 
   propagation modelling.

 * Simulation of underwater noise produced by environmental forcings 
   such as waves and rain.

 * Retrieval and processing of AIS data (ship position data).

 * Simulation of underwater noise produced by ships.

And potentially more ...

Some of these features can already be found in the [arlpy](https://github.com/org-arl/arlpy) package.

## Notebook tutorials

 1. [Extract bathymetry data from a matlab file](docs/demo_notebooks/read_bathy.ipynb)

 2. [Polar and planar coordinates](docs/demo_notebooks/coordinates.ipynb)

 3. [Interpolate bathymetry data](docs/demo_notebooks/interp_bathy.ipynb)