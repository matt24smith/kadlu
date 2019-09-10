import pytest
from datetime import datetime, timedelta
from kadlu.geospatial.data_sources import rdwps 
from kadlu.geospatial.data_sources.rdwps import Rdwps
from kadlu.geospatial.data_sources import fetch_util
from os.path import isfile

time = datetime.now() - timedelta(hours=6)

# mahone bay test area:
south =  44.4
north =  44.7
west  = -64.4
east  = -63.8


# disable fetch testing when not necessary to avoid slamming the API with automated requests
test_fetch = True 

def test_rdwps_fetch_windwaveswellheight():
    if not test_fetch: return
    filenames = Rdwps().fetch_windwaveswellheight(south=-90, north=90, west=-180, east=180, time=time)
    for fname in filenames:
        assert(isfile(fname))

def test_rdwps_fetch_windwaveheight():
    if not test_fetch: return
    filenames = Rdwps().fetch_windwaveheight(south=-90, north=90, west=-180, east=180, time=time)
    for fname in filenames:
        assert(isfile(fname))

def test_rdwps_fetch_wavedirection():
    if not test_fetch: return
    filenames = Rdwps().fetch_wavedirection(south=-90, north=90, west=-180, east=180, time=time)
    for fname in filenames:
        assert(isfile(fname))

def test_rdwps_fetch_waveperiod():
    if not test_fetch: return
    filenames = Rdwps().fetch_waveperiod(south=-90, north=90, west=-180, east=180, time=time)
    for fname in filenames:
        assert(isfile(fname))

def test_rdwps_fetch_wind_u():
    if not test_fetch: return
    filenames = Rdwps().fetch_wind_u(south=-90, north=90, west=-180, east=180, time=time)
    for fname in filenames:
        assert(isfile(fname))

def test_rdwps_fetch_wind_v():
    if not test_fetch: return
    filenames = Rdwps().fetch_wind_v(south=-90, north=90, west=-180, east=180, time=time)
    for fname in filenames:
        assert(isfile(fname))

def test_rdwps_fetch_icecover():
    if not test_fetch: return
    filenames = Rdwps().fetch_icecover(south=-90, north=90, west=-180, east=180, time=time)
    for fname in filenames:
        assert(isfile(fname))

def test_rdwps_region_abstraction():
    regions = rdwps.ll_2_regionstr(south=-90, north=90, west=-180, east=180)
    assert(len(regions) == 5)

    regions = rdwps.ll_2_regionstr(south=44.4, north=44.7, west=-64.4, east=-63.8)
    assert(len(regions) == 1)
    assert(regions[0] == 'gulf-st-lawrence')

    # TODO: add more assertions testing a single region boundary for each: 
    #       gulf-st-lawrence, erie, ontario, huron-michigan, superior

def test_rdwps_load_icecover():
    ice, lat, lon = Rdwps().load_icecover(south, north, west, east, time=time)

def test_rdwps_load_windwaveswellheight():
    height, lat, lon = Rdwps().load_windwaveswellheight(south, north, west, east, time=datetime(2019, 9, 9, 0, 0, 0, 0)-timedelta(hours=6))

