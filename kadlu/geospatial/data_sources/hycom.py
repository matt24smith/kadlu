"""
    Kadlu API for HYCOM data source

    Data source:
        https://www.hycom.org/data/glbv0pt08
    Web interface for hycom data retrieval:
        https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_53.X/data/2015.html
    Example of GET query for salinity:
        https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_53.X/data/2015.ascii?salinity[0:1:2][0:1:3][800:1:830][900:1:940]

    Oliver Kirsebom
    Casey Hilliard
    Matthew Smith 
    2019-09
"""

import numpy as np
import requests
from os.path import isfile
from kadlu.geospatial.data_sources.fetch_util import storage_cfg
from datetime import datetime
import warnings


def fetchname(fetchvar, slices):
    slicer = lambda tup, step=1 : f"[{tup[0]}:{step}:{tup[1]}]"
    return f"{fetchvar}{''.join(map(slicer, slices))}"


def fetch_grid():
    print("Fetching latitude and longitude grid from HYCOM...")
    url = "https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_53.X/data/2015.ascii?lat%5B0:1:3250%5D,lon%5B0:1:4499%5D"
    grid_ascii = requests.get(url)
    assert(grid_ascii.status_code == 200)

    meta, data = grid_ascii.text.split("---------------------------------------------\n")
    lat_csv, lon_csv = data.split("\n\n")[:-1]
    lat = np.array(lat_csv.split("\n")[1].split(", "), dtype=np.float)
    lon = np.array(lon_csv.split("\n")[1].split(", "), dtype=np.float)

    np.save(f"{storage_cfg()}hycom_lats.npy", lat, allow_pickle=False)
    np.save(f"{storage_cfg()}hycom_lons.npy", lon, allow_pickle=False)
    return


def dt_2_t(time):
    """ converts datetime to tuple: (year, (start_index, end_index)) """
    """
    units: hours since 2000-01-01 00:00:00
    time_origin: 2000-01-01 00:00:00
    calendar: gregorian
    axis: T
    NAVO_code: 13
    """
    warnings.warn("TODO: write the dt_2_t function")
    return "2015", (0, 2)


def load_grid():
    def _load_grid(storage_cfg): 
        return np.load(f"{storage_cfg}hycom_lats.npy"), np.load(f"{storage_cfg}hycom_lons.npy")
    try:
        return _load_grid(storage_cfg())
    except FileNotFoundError:
        fetch_grid()
        return _load_grid(storage_cfg())


def ll_2_xy(val, arr):
    """ converts lat/lon values to grid index """
    if val > arr[-1]: return len(arr) - 1
    return max(np.nonzero(arr >= val)[0][0] - 1, 0)


def fetch_hycom(year, slices, fetchvar):
    """
    year = '2015'       # string value between 2011? and 2015
    slices = [
        (0, 2),         # time: start, end 
        (0, 3),         # depth: top?, bottom?
        (800, 840),     # x grid index: lon min, lon max
        (900, 1000)     # y grid index: lat min, lat max
    ]
    fetchvar = 'salinity'

    returns: list of fetched filenames
    """
    # generate request
    source = f"https://tds.hycom.org/thredds/dodsC/GLBv0.08/expt_53.X/data/{year}.ascii?"
    payload_ascii = requests.get(f"{source}{fetchname(fetchvar, slices)}")
    assert(payload_ascii.status_code == 200)

    # parse response into numpy array
    meta, data = payload_ascii.text.split("---------------------------------------------\n")
    arrs = data.split("\n\n")[:-1]
    shape_str, payload = arrs[0].split("\n", 1)
    assert(shape_str[0:len(fetchvar)] == fetchvar)
    shape = tuple([int(x) for x in shape_str.split("[", 1)[1][:-1].split("][")])  # black magic list coercion
    output = np.ndarray(shape, dtype=np.float)
    for arr in payload.split("\n"):
        ix_str, row_csv = arr.split(", ", 1)
        a, b, c = [int(x) for x in ix_str[1:-1].split("][")]
        output[a][b][c] = np.array(row_csv.split(", "), dtype=np.int)

    np.save(f"{storage_cfg()}{year}{fetchname(fetchvar, slices)}.npy", output, allow_pickle=False)
    return [f"{storage_cfg()}{year}{fetchname(fetchvar, slices)}.npy"]


def load_hycom(year, slices, fetchvar, lat, lon):
    """
    not sure yet how this will work, i think best way is to save the data in the shape
    that was fetched, and let the shape destruction be done here.
    fetch_hycom can then check a "query hash" against pathnames of saved data (storage is cheap :)
    """
    # check for local files
    fname = f"{storage_cfg}{year}{fetchname(fetchvar, slices)}"
    if not isfile(fname): fetch_hycom(year, slices, fetchvar)

    # replace missing values with Nonetype
    lat[lat <= 2999] = None
    lon[lon <= 2999] = None
    data = np.load(f"{storage_cfg()}{year}{fetchname(fetchvar, slices)}.npy")
    return data, lat, lon


class Hycom():
    def fetch_salinity(self, south=-90, north=90, west=-180, east=180, time=datetime(2015, 1, 1)): 
        return fetch_hycom(
                    year=dt_2_t(time)[0],   # year
                    slices=[
                        dt_2_t(time)[1],    # time range: 0 -> 2 out of 2860 per year
                        (0, 3),             # depth range: 0 -> 3 out of 39 depth units ??
                        (ll_2_xy(west,  self.lon), ll_2_xy(east,  self.lon)),  # tuple: (xmin, xmax)
                        (ll_2_xy(south, self.lat), ll_2_xy(north, self.lat))   # tuple: (ymin, ymax)
                    ],
                    fetchvar='salinity'
                )
    def fetch_temp(self, south=-90, north=90, west=-180, east=180, time=datetime(2015, 1, 1)): 
        return fetch_hycom(
                    year=dt_2_t(time)[0],
                    slices=[
                        dt_2_t(time)[1],
                        (0, 3),
                        (ll_2_xy(west,  self.lon), ll_2_xy(east,  self.lon)),
                        (ll_2_xy(south, self.lat), ll_2_xy(north, self.lat))
                    ],
                    fetchvar='water_temp'
                )
    def fetch_water_u(self, south=-90, north=90, west=-180, east=180, time=datetime(2015, 1, 1)): 
        return fetch_hycom(
                    year=dt_2_t(time)[0],
                    slices=[
                        dt_2_t(time)[1],
                        (0, 3),
                        (ll_2_xy(west,  self.lon), ll_2_xy(east,  self.lon)),
                        (ll_2_xy(south, self.lat), ll_2_xy(north, self.lat))
                    ],
                    fetchvar='water_u'
                )
    def fetch_water_v(self, south=-90, north=90, west=-180, east=180, time=datetime(2015, 1, 1)): 
        return fetch_hycom(
                    year=dt_2_t(time)[0],
                    slices=[
                        dt_2_t(time)[1],
                        (0,3),
                        (ll_2_xy(west,  self.lon),  ll_2_xy(east,  self.lon)),
                        (ll_2_xy(south, self.lat),  ll_2_xy(north, self.lat))
                    ],
                    fetchvar='water_v'
                )
    def load_salinity(self, south=-90, north=90, west=-180, east=180, time=datetime(2015, 1, 1)): 
        return load_hycom(
                    year=dt_2_t(time)[0],
                    slices=[
                        dt_2_t(time)[1],    # time range: 0 -> 2 out of 2860 per year
                        (0, 3),             # depth range: 0 -> 3 out of 39 depth units ??
                        (ll_2_xy(west,  self.lon),  ll_2_xy(east,  self.lon)),  # tuple: (xmin, xmax)
                        (ll_2_xy(south, self.lat),  ll_2_xy(north, self.lat))   # tuple: (ymin, ymax)
                    ],
                    fetchvar='salinity', 
                    lat=self.lat,
                    lon=self.lon
                )
    def load_temp(self, south=-90, north=90, west=-180, east=180, time=datetime(2015, 1, 1)): 
        return load_hycom(
                    year=dt_2_t(time)[0],
                    slices=[
                        dt_2_t(time)[1],    # time range: 0 -> 2 out of 2860 per year
                        (0, 3),             # depth range: 0 -> 3 out of 39 depth units ??
                        (ll_2_xy(west,  self.lon),  ll_2_xy(east,  self.lon)),  # tuple: (xmin, xmax)
                        (ll_2_xy(south, self.lat),  ll_2_xy(north, self.lat))   # tuple: (ymin, ymax)
                    ],
                    fetchvar='water_temp', 
                    lat=self.lat,
                    lon=self.lon
                )
    def load_water_u(self, south=-90, north=90, west=-180, east=180, time=datetime(2015, 1, 1)): 
        return load_hycom(
                    year=dt_2_t(time)[0],
                    slices=[
                        dt_2_t(time)[1],    # time range: 0 -> 2 out of 2860 per year
                        (0, 3),             # depth range: 0 -> 3 out of 39 depth units ??
                        (ll_2_xy(west,  self.lon),  ll_2_xy(east,  self.lon)),  # tuple: (xmin, xmax)
                        (ll_2_xy(south, self.lat),  ll_2_xy(north, self.lat))   # tuple: (ymin, ymax)
                    ],
                    fetchvar='water_u',
                    lat=self.lat,
                    lon=self.lon
                )
    def load_water_v(self, south=-90, north=90, west=-180, east=180, time=datetime(2015, 1, 1)): 
        return load_hycom(
                    year=dt_2_t(time)[0],
                    slices=[
                        dt_2_t(time)[1],    # time range: 0 -> 2 out of 2860 per year
                        (0, 3),             # depth range: 0 -> 3 out of 39 depth units ??
                        (ll_2_xy(west,  self.lon),  ll_2_xy(east,  self.lon)),  # tuple: (xmin, xmax)
                        (ll_2_xy(south, self.lat),  ll_2_xy(north, self.lat))   # tuple: (ymin, ymax)
                    ],
                    fetchvar='water_v', 
                    lat=self.lat,
                    lon=self.lon
                )
    def __str__(self):
        info = '\n'.join(["Native hycom .[ab] data converted to NetCDF at the Naval Research Laboratory,",
            "interpolated to a uniform 0.08° between 40°S-40°N (0.04° poleward of these latitudes)," ,
            "and interpolated to 40 standard z-levels.",
            "Available class functions:\n\t"])
        fcns = [fcn for fcn in dir(self) if callable(getattr(self, fcn)) and not fcn.startswith("__")]
        args = "(south=-90, north=90, west=-180, east=180, time=datetime(2015, 1, 1))"
        return info + "\n\t".join(map(lambda f : f"{f}{'     '[len(f)-9:]}{args}", fcns ))
    def __init__(self):
        self.lat, self.lon = load_grid()


"""
print(Hycom())

mahone bay test area:
south =  44.4
north =  44.7
west  = -64.4
east  = -63.8
time  = datetime(2015, 1, 1)

salinity, lat, lon = Hycom().load_salinity(south=south, north=north, west=west, east=east, time=datetime) 
temp, lat, lon = Hycom().load_temp(south=south, north=north, west=west, east=east, time=datetime) 
water_u, lat, lon = Hycom().load_water_u(south=south, north=north, west=west, east=east, time=datetime) 
water_v, lat, lon = Hycom().load_water_v(south=south, north=north, west=west, east=east, time=datetime) 
"""

