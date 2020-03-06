"""
    API for NONNA-100 Bathymetric Data from the Canadian Hydrographic Service (CHS)
     
    Metadata regarding the dataset can be found here:
        https://open.canada.ca/data/en/dataset/d3881c4c-650d-4070-bf9b-1e00aabf0a1d
"""

import os
import json
import requests
import warnings
from datetime import datetime

import numpy as np
from osgeo import gdal

import kadlu.geospatial.data_sources.source_map
from kadlu.geospatial.data_sources.data_util        import          \
        database_cfg,                                               \
        storage_cfg,                                                \
        insert_hash,                                                \
        serialized,                                                 \
        chs_table,                                                  \
        str_def


conn, db = database_cfg()


def parse_sw_corner(path):
    """ return the southwest corner coordinates for a given bathymetry file """
    fname = os.path.basename(path)
    south = int(fname[4:8]) / 100
    west = -int(fname[9:14]) / 100
    assert west >= -180 and west <= 180, 'Invalid parsed longitude value'
    assert south >= -90 and south <= 90, 'Invalid parsed latitude value'
    return south, west


def fetch_chs(south, north, west, east, band_id=1):
    """ download bathymetric geotiffs, process them, and insert into db

        args:
            south, north: float
                ymin, ymax coordinate boundaries. range: -90, 90
            west, east: float
                xmin, xmax coordinate boundaries. range: -180, 180

        return: 
            True if new data was downloaded and processed, else False
    """

    # api call: get raster IDs within bounding box
    source = "https://gisp.dfo-mpo.gc.ca/arcgis/rest/services/FGP/CHS_NONNA_100/"
    spatialRel = "esriSpatialRelIntersects"
    spatialReference = "4326"  # WGS-84 spec
    geometry = json.dumps({"xmin":west, "ymin":south, "xmax":east, "ymax":north})
    url1 = f"{source}ImageServer/query?geometry={geometry}&returnIdsOnly=true&geometryType=esriGeometryEnvelope&spatialRel={spatialRel}&f=json&outFields=*&inSR={spatialReference}"
    req1 = requests.get(url1)
    assert(req1.status_code == 200)
    assert("error" not in json.loads(req1.text).keys())

    # api call: query for resource locations of rasters
    imgs = []
    rasterIds = json.loads(req1.text)['objectIds']
    assert(len(rasterIds) > 0)
    for chunk in range(0, int(len(rasterIds) / 20) + 1):  # max request size is 20 at a time
        rasterIdsCSV = ','.join([f"{x}" for x in rasterIds[chunk * 20:(chunk+1) * 20]])
        url2 = f"{source}ImageServer/download?geometry={geometry}&geometryType=esriGeometryPolygon&format=TIFF&f=json&rasterIds={rasterIdsCSV}"
        req2 = requests.get(url2)
        assert(req2.status_code == 200)
        jsondata = json.loads(req2.text)
        assert("error" not in jsondata.keys())
        imgs += [img for img in jsondata['rasterFiles'] if 'CA2' in img['id']]

    # api call: for each tiff image, download the associated rasters
    filepaths = []
    imgnum = 1
    for img in imgs:
        fname = img['id'].split('\\')[-1]
        fpath = f"{storage_cfg()}{fname}"
        filepaths.append(fpath)
        if os.path.isfile(fpath): 
            #print(f'CHS {fname} bathymetry: file found, skipping download')
            pass
        else:
            print(f"CHS {fname} bathymetry: downloading {imgnum}/{len(imgs)} "
                   "from CHS NONNA-100...")
            assert(len(img['rasterIds']) == 1)
            url3 = f"{source}ImageServer/file?id={img['id'][0:]}&rasterId={img['rasterIds'][0]}"
            tiff = requests.get(url3)
            assert(tiff.status_code == 200)
            with open(fpath, "wb") as f: f.write(tiff.content)
            imgnum += 1

    print(f'CHS bathymetry: processing {len(filepaths)} '
          f'file{"s" if len(filepaths)!=1 else ""}')

    # read downloaded files and process them for DB insertion
    for filepath in filepaths:
        tiff_data = gdal.Open(filepath)
        band = tiff_data.GetRasterBand(band_id)
        values = tiff_data.ReadAsArray()
        bathy = np.ma.masked_invalid(values)

        # generate latlon arrays
        file_south, file_west = parse_sw_corner(filepath)
        dlat = 0.001
        if file_south < 68:
            dlon = 0.001
        elif file_south >=68 and file_south < 80:
            dlon = 0.002
        elif file_south >= 80:
            dlon = 0.004
        file_ymax = tiff_data.RasterYSize*dlat+file_south
        file_xmax = tiff_data.RasterXSize*dlon+file_west
        file_lat = np.linspace(start=file_south, stop=file_ymax, num=tiff_data.RasterYSize)
        file_lon = np.linspace(start=file_west,  stop=file_xmax, num=tiff_data.RasterXSize)

        # select non-masked entries, remove missing, build grid
        z1 = np.flip(bathy, axis=0)
        x1, y1 = np.meshgrid(file_lon, file_lat)
        ix = z1[~z1.mask] != band.GetNoDataValue()
        x2 = x1[~z1.mask][ix]
        y2 = y1[~z1.mask][ix]
        z2 = np.abs(z1[~z1.mask][ix].data)
        source = ['chs' for z in z2]
        grid = list(map(tuple, np.vstack((z2, y2, x2, source)).T))

        # insert into db
        n1 = db.execute(f"SELECT COUNT(*) FROM {chs_table}").fetchall()[0][0]
        db.executemany(f"INSERT OR IGNORE INTO {chs_table} VALUES (?,?,?,?)", grid)
        n2 = db.execute(f"SELECT COUNT(*) FROM {chs_table}").fetchall()[0][0]
        db.execute("COMMIT")
        conn.commit()
        print(f"CHS {filepath.split('/')[-1]} bathymetry: "
              f"processed and inserted {n2-n1} rows. "
              f"{len(z1[~z1.mask]) - len(grid)} null values removed, "
              f"{len(grid) - (n2-n1)} duplicate rows ignored")

    return True


def load_chs(south, north, west, east):
    """ load bathymetric data from the database

        args:
            south, north:
                y-grid coordinate boundaries (float)
            west, east:
                x-grid coordinate boundaries (float)

        return:
            bathy:
                bathymetric values within query range
            lat:
                y-grid coordinate values
            lon:
                x-grid coordinate values
    """
    # check for missing data
    qryargs = dict(
            south=south, west=west,
            north=north, east=east, 
            start=datetime.now(), end=datetime.now())
    kadlu.geospatial.data_sources.source_map.fetch_handler(
            'bathy', 'chs', parallel=1, **qryargs)

    # load the data
    db.execute(' AND '.join([f"SELECT * FROM {chs_table} WHERE lat >= ?",
                                                              "lat <= ?",
                                                              "lon >= ?",
                                                              "lon <= ?"]),
               tuple(map(str, [south, north, west, east])))
    
    slices = np.array(db.fetchall(), dtype=object).T
    assert len(slices) == 4, "no data found for query range"
    bathy, lat, lon, source = slices
    return np.array((bathy, lat, lon)).astype(float)


class Chs():
    """ collection of module functions for fetching and loading """

    def fetch_bathymetry(self, **kwargs):
        # trim query indexing entropy and check for fetched data
        for k in ('start', 'lock', 'end', 'top', 'bottom'):
            if k in kwargs.keys(): del kwargs[k]
        if serialized(kwargs, 'fetch_chs_bathy'): return False

        # if new data was fetched, index the query hash
        if (fetch_chs(south=kwargs['south'], north=kwargs['north'], 
                west=kwargs['west'], east=kwargs['east'], band_id=1)):
            insert_hash(kwargs, 'fetch_chs_bathy')
        return True

    def load_bathymetry(self, **kwargs):
        return load_chs(south=kwargs['south'], north=kwargs['north'], 
              west=kwargs['west'], east=kwargs['east'])

    def __str__(self):
        info = "\n".join(["Non-Navigational 100m (NONNA-100) bathymetry dataset",
            "from the Canadian Hydrographic Datastore",
            "\thttps://open.canada.ca/data/en/dataset/d3881c4c-650d-4070-bf9b-1e00aabf0a1d"])
        args = "(south, north, west, east)"
        return str_def(self, info, args)


