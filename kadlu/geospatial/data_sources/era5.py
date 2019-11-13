"""
    API for Era5 dataset from Copernicus Climate Datastore

    Metadata regarding the dataset can be found here:
        https://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-single-levels?tab=overview

    Oliver Kirsebom
    Casey Hilliard
    Matthew Smith
"""

import cdsapi
import numpy as np
import pygrib
import os
from datetime import datetime, timedelta
import warnings

from kadlu.geospatial.data_sources.fetch_util import \
storage_cfg, database_cfg, str_def, plot_sample_grib, dt_2_epoch, epoch_2_dt


conn, db = database_cfg()


def fetchname(wavevar, time):
    return f"ERA5_reanalysis_{wavevar}_{time.strftime('%Y-%m-%d_%Hh')}.grb2"


def fetch_era5(wavevar, start, end):
    """ return list of filenames containing era5 data for time range

    args:
        wavevar: string
            the variable short name of desired wave parameter according to ERA5 docs
            the complete list can be found here (table 7 for wave params)
            https://confluence.ecmwf.int/display/CKB/ERA5+data+documentation#ERA5datadocumentation-Temporalfrequency
        start: datetime
            the beginning of the desired time range
        end: datetime
            the end of the desired time range

    return:
        fetchfiles: list
            a list of strings describing complete filepaths of downloaded data
    """
    time = datetime(start.year, start.month, start.day, start.hour)
    #fetchfiles = []

    while time <= end:
        fname= f"{storage_cfg()}{fetchname(wavevar, time)}"
        print(f"Downloading {fetchname(wavevar, time)} from Copernicus Climate Data Store...")
        c = cdsapi.Client()
        try:
            c.retrieve('reanalysis-era5-single-levels', {
                'product_type'  : 'reanalysis',
                'format'        : 'grib',
                'variable'      : wavevar,
                'year'          : time.strftime("%Y"),
                'month'         : time.strftime("%m"),
                'day'           : time.strftime("%d"),
                'time'          : time.strftime("%H:00")
            }, fname)
        except Exception:
            warnings.warn(f"No data for {time.ctime()}")
            time += timedelta(hours=1)
            continue

    #    fetchfiles.append(fname)
    #    time += timedelta(hours=1)
    #for fname in fetchfiles:
        grib = pygrib.open(fname)
        assert(grib.messages == 1)
        msg = grib[1]
        z, y, x = msg.data()
        x -= 180  # normalize longitudes

        # build index to collect points in area of interest
        #latix = np.array([l >= south and l <= north for l in y[~z.mask]])
        #lonix = np.array([l >= west and l <= east for l in x[~z.mask]])
        #ix = latix & lonix

        # build coordinate grid and insert into db
        src = ['era5' for item in z[~z.mask]]
        t = dt_2_epoch([time for item in z[~z.mask]])
        grid = list(map(tuple, np.vstack((z[~z.mask].data, y[~z.mask], x[~z.mask], t, src)).T))
        n1 = db.execute(f"SELECT COUNT(*) FROM {wavevar}").fetchall()[0][0]
        db.executemany(f"INSERT OR IGNORE INTO {wavevar} VALUES (?,?,?,?,?)", grid)
        n2 = db.execute(f"SELECT COUNT(*) FROM {wavevar}").fetchall()[0][0]
        db.execute("COMMIT")
        conn.commit()

        print(f"{fname.split('/')[-1]} processed and inserted {n2-n1} rows. "
              f"{(z.shape[0]*z.shape[1])-len(z[~z.mask])} null values removed, "
              f"{len(grid) - (n2-n1)} duplicate rows ignored")

        time += timedelta(hours=1)

    return #fetchfiles

def load_era5(wavevar, start, end, south, north, west, east):
    db.execute(' AND '.join([f"SELECT * FROM {wavevar} WHERE lat >= ?",
                                                            "lat <= ?",
                                                            "lon >= ?",
                                                            "lon <= ?",
                                                           "time >= ?",
                                                           "time <= ?"]),
               tuple(map(str, [south, north, west, east, 
                               dt_2_epoch(start), dt_2_epoch(end)])))
    val, lat, lon, time, source = np.array(db.fetchall(), dtype=object).T
    return val, lat, lon, epoch_2_dt(time)

#def load_era5(wavevar, start, end, south, north, west, east, plot):
#    """ return era5 wave data for specified wave parameter within given time and spatial boundaries
#
#    args:
#        wavevar: string
#            the variable short name of desired wave parameter according to ERA5 docs
#            the complete listing can be found here (table 7 for wave params)
#            https://confluence.ecmwf.int/display/CKB/ERA5+data+documentation#ERA5datadocumentation-Temporalfrequency
#        start: datetime
#            the beginning of the desired time range
#        end: datetime
#            the end of the desired time range
#        south, north: float
#            ymin, ymax coordinate boundaries (latitude). range: -90, 90
#        west, east: float
#            xmin, xmax coordinate boundaries (longitude). range: -180, 180
#        plot: boolean
#            if true a plot will be output (experimental feature)
#    """
#    fetchfiles = []  # used for plotting, this may be removed later
#    val = np.array([])
#    lat = np.array([])
#    lon = np.array([])
#    timestamps = np.array([])
#    time = datetime(start.year, start.month, start.day, start.hour)
#    assert(time <= end)
#
#    print(f"Loading {wavevar} from {int((end-start).total_seconds() /60 /60)+1} hourly global data files")
#
#    while time <= end:
#        # get the filename
#        fname = f"{storage_cfg()}{fetchname(wavevar, time)}" 
#        fetchfiles.append(fname)  # used for plotting
#        if not os.path.isfile(fname): fetch_era5(wavevar, time, time)
#
#        # open the file and get the raw data
#        grib = pygrib.open(fname)
#        assert(grib.messages == 1)
#        msg = grib[1]
#        z, y, x = msg.data()
#        x -= 180  # normalize longitudes
#
#        # build index to collect points in area of interest
#        #latix = np.array([l >= south and l <= north for l in y[~z.mask]])
#        #lonix = np.array([l >= west and l <= east for l in x[~z.mask]])
#        latix = np.array([l >= south and l <= north for l in y[~z.mask]])
#        lonix = np.array([l >= west and l <= east for l in x[~z.mask]])
#        ix = latix & lonix
#
#        # append points within AoI to return arrays
#        val = np.append(val, z[~z.mask][ix])
#        lat = np.append(lat, y[~z.mask][ix])
#        lon = np.append(lon, x[~z.mask][ix])
#        timestamps = np.append(timestamps, [time for x in range(sum(ix))])
#
#        time += timedelta(hours=1)
#
#    if plot is not False: plot_sample_grib(fetchfiles, plot)
#    return val.data, lat, lon, timestamps


class Era5():
    """ collection of module functions for fetching and loading. abstracted to include a seperate function for each variable """

    def fetch_windwaveswellheight(self, south=-90, north=90, west=-180, east=180, start=datetime.now()-timedelta(hours=24), end=datetime.now()):
        return fetch_era5('significant_height_of_combined_wind_waves_and_swell', start, end)
    def fetch_wavedirection(self, south=-90, north=90, west=-180, east=180, start=datetime.now()-timedelta(hours=24), end=datetime.now()):
        return fetch_era5('mean_wave_direction', start, end)
    def fetch_waveperiod(self, south=-90, north=90, west=-180, east=180, start=datetime.now()-timedelta(hours=24), end=datetime.now()):
        return fetch_era5('mean_wave_period', start, end)

    def load_windwaveswellheight(self, south=-90, north=90, west=-180, east=180, start=datetime.now()-timedelta(hours=24), end=datetime.now()):
        return load_era5('significant_height_of_combined_wind_waves_and_swell', start, end, south, north, west, east)
    def load_wavedirection(self, south=-90, north=90, west=-180, east=180, start=datetime.now()-timedelta(hours=24), end=datetime.now()):
        return load_era5('mean_wave_direction', start, end, south, north, west, east)
    def load_waveperiod(self, south=-90, north=90, west=-180, east=180, start=datetime.now()-timedelta(hours=24), end=datetime.now()):
        return load_era5('mean_wave_period', start, end, south, north, west, east)

    def __str__(self):
        info = '\n'.join([
                "Era5 Global Dataset from Copernicus Climate Datastore",
                "\thttps://cds.climate.copernicus.eu/cdsapp#!/dataset/reanalysis-era5-single-levels?tab=overview"
            ])
        args = "(south=-90, north=90, west=-180, east=180, start=datetime(), end=datetime())"
        return str_def(self, info, args)

