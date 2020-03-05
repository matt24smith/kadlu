"""
    Utilities for data fetching and loading.
"""

import os
import sys
import json
import pickle
import sqlite3
import warnings
import configparser
from os import path
from os.path import dirname
from hashlib import md5
from functools import reduce
from datetime import datetime, timedelta
from contextlib import contextmanager, redirect_stdout, redirect_stderr

import numpy as np


# database tables for data fetching and loading
chs_table    = 'bathy'
hycom_tables = ['salinity', 'water_temp', 'water_u', 'water_v']
wwiii_tables = ['hs', 'dp', 'tp', 'windU', 'windV']
era5_tables  = [
        'significant_height_of_combined_wind_waves_and_swell',
        'mean_wave_direction',
        'mean_wave_period',
        'u_component_of_wind',
        'v_component_of_wind'
    ]


cfg = configparser.ConfigParser()       # read .ini into dictionary object
cfg.read(path.join(path.dirname(dirname(dirname(dirname(__file__)))), "config.ini"))


def storage_cfg():
    """ return filepath containing storage configuration string

        first checks the config.ini file in kadlu root folder, then
        defaults to kadlu/storage
    """

    def default_storage(msg):
        """ helper function for storage_cfg() """
        storage_location = (path.abspath(path.dirname(dirname(dirname(dirname(__file__))))) + "/storage/")
        if not os.path.isdir(storage_location):
            os.mkdir(storage_location)
        #print(f"NOTICE: {msg} storage location will be set to {storage_location}")
        return storage_location

    try:
        storage_location = cfg["storage"]["storage_location"]
    except KeyError:                        # missing config.ini file
        return default_storage("missing kadlu/config.ini.")

    if storage_location == '':              # null value in config.ini
        return default_storage("null value in kadlu/config.ini.")

    if not path.isdir(storage_location):    # verify the location exists
        return default_storage("storage location doesn't exist.")

    return storage_location


def database_cfg():
    """ configure and connect to sqlite database

        time is stored as an integer in the database, where each value
        is epoch hours since 2000-01-01 00:00

        returns:
            conn:   
                database connection object
            db:
                connection cursor object
    """
    conn = sqlite3.connect(storage_cfg() + "geospatial.db")
    db = conn.cursor()

    # bathymetry table (CHS)
    db.execute(f"CREATE TABLE IF NOT EXISTS {chs_table}  "
               "(   val     REAL    NOT NULL, "
               "    lat     REAL    NOT NULL, "
               "    lon     REAL    NOT NULL, "
               "    source  TEXT    NOT NULL )") 
    db.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS "
               f"idx_{chs_table} on {chs_table}(lon, lat, val, source)")

    # hycom environmental data tables
    for var in hycom_tables:
        db.execute(f"CREATE TABLE IF NOT EXISTS {var}"
                    "( val     REAL NOT NULL, "
                    "  lat     REAL NOT NULL, "
                    "  lon     REAL NOT NULL, "
                    "  time    INT  NOT NULL, "
                    "  depth   INT  NOT NULL, "
                    "  source  TEXT NOT NULL )")
        db.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS "
                   f"idx_{var} on {var}(time, lon, lat, depth, val, source)")

    # wave data tables
    for var in era5_tables + wwiii_tables:
        db.execute(f"CREATE TABLE IF NOT EXISTS {var}"
                    "( val     REAL    NOT NULL, "
                    "  lat     REAL    NOT NULL, "
                    "  lon     REAL    NOT NULL, "
                    "  time    INT     NOT NULL, "
                    "  source  TEXT    NOT NULL )") 
        db.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS "
                   f"idx_{var} on {var}(time, lon, lat, val, source)")

    db.execute("CREATE TABLE IF NOT EXISTS fetch_map"
                '(  hash    INT  NOT NULL,  '
                '   bytes   BLOB           )' )
    db.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS "
                 f"idx_fetched on fetch_map(hash)")

    # this is just for a fun demo and should be removed later
    db.execute('CREATE TABLE IF NOT EXISTS blockchain'
               '( count     INT     NOT NULL, '
               '  hash      INT     NOT NULL )')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_blockchain ON blockchain(count)')

    return conn, db


def bin_db():
    """ database for storing serialized objects in memory 
        
        code was previously used for caching results quickly but
        is currently not in use
    """
    conn = sqlite3.connect('file::memory:?cache=shared', uri=True)
    db = conn.cursor()
    db.execute('CREATE TABLE IF NOT EXISTS bin'
                '(  hash    INT  NOT NULL,  '
                '   bytes   BLOB NOT NULL  )' )
    db.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS "
                 f"idx_bin on bin(hash)")

    raise ResourceWarning('fcn not used')
    #return conn, db


def hash_key(kwargs, seed, 
        keep=('south','west', 'north', 'east', 'top', 'bottom', 'start', 'end')):
    """ compute unique hash and convert to 8-byte int as serialization key """
    qry = kwargs.copy()
    dim = kwargs.keys()
    for dimension in dim:
        if dimension not in keep: del qry[dimension]
    string = seed + json.dumps(qry, sort_keys=True, default=str)
    key = int(md5(string.encode('utf-8')).hexdigest(), base=16) >> 80
    #return key >> 80  # bitshift value by 80 bits: SQLite max value is 64 bits
    return key


def insert_hash(kwargs, seed='', obj=None):
    """ create hash index in database to record query history.
        this is used for mapping the coverage of fetched data.
        optionally include an object to be serialized and cached
    """
    qry = kwargs.copy()
    conn, db = database_cfg()
    if 'lock' in qry.keys(): del qry['lock']
    key = hash_key(qry, seed)
    #update_blockchain(key, seed)  # easter egg
    db.execute('INSERT OR IGNORE INTO fetch_map VALUES (?,?)',
               (key, pickle.dumps(obj)))
    conn.commit()
    return


def serialized(kwargs, seed=''):
    """ returns true if fetch query hash exists in database else False """
    key = hash_key(kwargs, seed)
    if 'lock' in kwargs.keys(): kwargs['lock'].acquire()
    conn, db = database_cfg()
    db.execute('SELECT * FROM fetch_map WHERE hash == ?', (key,))
    res = db.fetchone()
    if 'lock' in kwargs.keys(): kwargs['lock'].release()
    if res is None: return False
    if res[1] is not None: return res[1]
    return True


def dt_2_epoch(dt_arr):
    """ convert datetimes to epoch hours """
    t0 = datetime(2000, 1, 1, 0, 0, 0)
    delta = lambda dt: (dt - t0).total_seconds()/60/60
    if isinstance(dt_arr, (list, np.ndarray)): return list(map(int, map(delta, dt_arr)))
    elif isinstance(dt_arr, (datetime)): return int(delta(dt_arr))
    else: raise ValueError('input must be datetime or array of datetimes')


def epoch_2_dt(ep_arr):
    """ convert epoch hours to datetimes """
    t0 = datetime(2000, 1, 1)
    delta = lambda ep : t0 + timedelta(hours=ep)
    if isinstance(ep_arr, (list, np.ndarray)): return list(map(delta, ep_arr))
    elif isinstance(ep_arr, (float, int)): return delta(ep_arr)
    else: raise ValueError('input must be integer or array of integers')


def index(val, sorted_arr):
    """ converts value in coordinate array to grid index """
    if val > sorted_arr[-1]: return len(sorted_arr) - 1
    return np.nonzero(sorted_arr >= val)[0][0]


def flatten(cols, frames):
    """ dimensional reduction by taking average of time frames """
    # assert that frames are of equal size
    assert len(cols) == 5
    assert reduce(lambda a, b: (a==b)*a, frames[1:] - frames[:-1])

    # aggregate time frame splits and reduce them to average
    frames_ix = np.append([0], frames)
    split_num = range(len(frames_ix) -1)
    val_split = np.array([cols[0][frames_ix[f] : frames_ix[f+1]] for f in split_num])
    value_avg = (reduce(np.add, val_split) / len(val_split))
    _, y, x, _, z = cols[:, frames_ix[0] : frames_ix[1]]
    return value_avg, y, x, z


def reshape_2D(cols):
    return dict(values=cols[0], lats=cols[1], lons=cols[2])


def reshape_3D(cols):
    """ prepare loaded data for interpolation """
    if isinstance(cols[0], (float, int)):
        return dict(values=cols[0])
    frames = np.append(np.nonzero(cols[3][1:] > cols[3][:-1])[0] + 1, len(cols[3]))
    if len(np.unique(frames)) > 1: vals, y, x, z = flatten(cols, frames) 
    else: vals, y, x, _, z  = cols
    rows = np.array((vals, y, x, z)).T

    # reshape row data to 3D array
    xgrid, ygrid, zgrid = np.unique(x), np.unique(y), np.unique(z)
    gridspace = np.full((len(ygrid), len(xgrid), len(zgrid)), fill_value=-30000)
    # this could potentially be optimized to avoid an index lookup cost
    for row in rows:
        x_ix = index(row[2], xgrid)
        y_ix = index(row[1], ygrid)
        z_ix = index(row[3], zgrid)
        gridspace[y_ix, x_ix, z_ix] = row[0]

    # remove -30000 values for interpolation:
    # fill missing depth values with last value in each column
    # this section could be cleaned up
    for xi in range(0, gridspace.shape[0]):
        for yi in range(0, gridspace.shape[1]):
            col = gridspace[xi, yi]
            if sum(col == -30000) > 0 and sum(col == -30000) < len(col):
                col[col == -30000] = col[col != -30000][-1]
                gridspace[xi, yi] = col

    # TODO:
    # create default values for columns that are entirely null

    return dict(values=gridspace, lats=ygrid, lons=xgrid, depths=zgrid)


def str_def(self, info, args):
    """ builds string definition for data source class objects """
    fcns = [fcn for fcn in dir(self) if callable(getattr(self, fcn)) 
            and 'load' in fcn and not fcn.startswith("__")]
    return (f'{info}\n\nfunction input arguments:\n\t{args}\n\nclass functions:\n\t'
            + '\n\t'.join(fcns) + '\n')


@contextmanager
def dev_null():
    """ context manager to redirect output to /dev/null """
    with open(os.devnull, 'w') as null:
        try:
            with redirect_stderr(null) as err, redirect_stdout(null) as out: 
                yield (err, out)
        finally:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__


class Boundary():
    """ compute intersecting boundaries with separating axis theorem """
    def __init__(self, south, north, west, east, fetchvar=''):
        self.south, self.north, self.west, self.east, self.fetchvar = \
                south, north, west, east, fetchvar

    def __str__(self): return self.fetchvar

    def intersects(self, other):  # separating axis theorem
        return not (self.east  < other.west or
                    self.west  > other.east or
                    self.north < other.south or
                    self.south > other.north)


def ll_2_regionstr(south, north, west, east, regions, default=[]):
    """ convert input bounds to region strings with seperating axis theorem """
    if west > east:  # recursive function call if query intersects antimeridian
        return np.union1d(ll_2_regionstr(south, north, west, +180, regions, default), 
                          ll_2_regionstr(south, north, -180, east, regions, default))

    query = Boundary(south, north, west, east)
    matching = [str(reg) for reg in regions if query.intersects(reg)]

    if len(matching) == 0: 
        warnings.warn(f"No regions matched for query. Defaulting to {default} ({len(default)} regions)")
        return default

    return np.unique(matching)


def update_blockchain(curkey, seed=''):
    """ this is just for fun and isnt actually useful """
    conn, db = database_cfg()

    db.execute('SELECT * FROM blockchain ORDER BY count DESC LIMIT 1')
    res = db.fetchone()
    oldcount, oldhash = res if res is not None else 0, 0

    newkey = (str(oldhash) + str(curkey) + seed).encode('UTF-8')
    newhash = int(md5(newkey).hexdigest(), base=16) >> 80

    sql = 'INSERT INTO blockchain VALUES (?,?)'
    db.execute(sql, (oldcount+1, newhash))
    conn.commit()

    print(f'the blockchain has a chain size of {oldcount+1} blocks. newest block: {newhash}')
    return


class DataUtil():
    """ user API for data utils """
    def epoch_2_dt(arr):    return epoch_2_dt(arr)
    def dt_2_epoch(arr):    return dt_2_epoch(arr)
    def database_cfg():     return database_cfg()
    def index(sorted_arr):  return index(sorted_arr)
    def reshape_2D(cols):   return reshape_2D(cols)
    def reshape_3D(cols):   return reshape_3D(cols)


