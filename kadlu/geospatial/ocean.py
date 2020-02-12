import numpy as np
from multiprocessing import Process, Queue
from kadlu.geospatial.interpolation             import      \
        Interpolator2D,                                     \
        Interpolator3D,                                     \
        Uniform2D,                                          \
        Uniform3D
from kadlu.geospatial.data_sources.data_util    import      \
        reshape_2D,                                         \
        reshape_3D,                                         \
        dt_2_epoch
from kadlu.geospatial.data_sources.chs          import Chs
#from kadlu.geospatial.data_sources.gebco        import Gebco
from kadlu.geospatial.data_sources.hycom        import Hycom
from kadlu.geospatial.data_sources.era5         import Era5
from kadlu.geospatial.data_sources.wwiii        import Wwiii


# dicts for mapping strings to callback functions
fetch_map = dict(
        bathy_chs           = Chs().fetch_bathymetry,
        #bathy_gebco         = Gebco().fetch_bathymetry, 
        temp_hycom          = Hycom().fetch_temp,
        salinity_hycom      = Hycom().fetch_salinity,
        wavedir_era5        = Era5().fetch_wavedirection,
        waveheight_era5     = Era5().fetch_windwaveswellheight,
        waveperiod_era5     = Era5().fetch_waveperiod,
        windspeed_era5      = Era5().fetch_wind,
        wavedir_wwiii       = Wwiii().fetch_wavedirection,
        waveheight_wwiii    = Wwiii().fetch_windwaveheight,
        waveperiod_wwiii    = Wwiii().fetch_waveperiod,
        windspeed_wwiii     = Wwiii().fetch_wind
    )
load_map = dict(
        bathy_chs           = Chs().load_bathymetry,
        #bathy_gebco         = Gebco().load_bathymetry, 
        temp_hycom          = Hycom().load_temp,
        salinity_hycom      = Hycom().load_salinity,
        wavedir_era5        = Era5().load_wavedirection,
        wavedir_wwiii       = Wwiii().load_wavedirection,
        waveheight_era5     = Era5().load_windwaveswellheight,
        waveheight_wwiii    = Wwiii().load_windwaveheight,
        waveperiod_era5     = Era5().load_waveperiod,
        waveperiod_wwiii    = Wwiii().load_waveperiod,
        windspeed_era5      = Era5().load_wind,
        windspeed_wwiii     = Wwiii().load_wind
    )


def worker(interpfcn, reshapefcn, cols, var, q):
    """ compute interpolation in parallel worker process
    
        interpfcn:
            callback function for interpolation
        reshapefcn:
            callback function for reshaping row data into matrix format
            for interpolation
        data:
            data as returned from load function
        q:
            shared queue object to pass binary back to parent
    """
    obj = interpfcn(**reshapefcn(cols))
    q.put((var, obj))
    return


def load_callback(*, data, v, **kwargs):
    """ bootstrap data into callable to prepare for parallelization """
    return [data[key] for key in 
               (f'{v}_val',f'{v}_lat',f'{v}_lon', f'{v}_time',f'{v}_depth')
               if key in data.keys()]


class Ocean():
    """ class for handling ocean data requests 

        data will be loaded using the given data sources and boundaries
        from arguments. an interpolation for each variable will be computed in 
        parallel

        data will be averaged over time frames for interpolation. for finer
        temporal resolution, define smaller time boundaries

        any of the below load_args may also accept a callback function instead
        of a string or array value if you wish to write your own data loading
        function. the boundary arguments supplied here will be passed to the 
        callable, i.e. north, south, west, east, top, bottom, start, end

        bles or array arguments must be ordered by [val, lat, lon] for 2D 
        data, or [val, lat, lon, depth] for 3D data

        args:
            load_bathymetry: 
                source of bathymetry data. can be 'chs' to load previously 
                fetched data, or array ordered by [val, lat, lon]
            load_temp:
                source of temperature data. can be 'hycom' to load previously
                fetched data, or array ordered by [val, lat, lon, depth]
            load_salinity:
                source of salinity data. can be 'hycom' to load previously
                fetched data, or array ordered by [val, lat, lon, depth]
            load_wavedir:
                source of wave direction data. can be 'era5' or 'wwiii' to load
                previously fetched data, or array ordered by [val, lat, lon]
            load_waveheight:
                source of wave height data. can be 'era5' or 'wwiii' to load
                previously fetched data, or array ordered by [val, lat, lon]
            load_waveperiod:
                source of wave period data. can be 'era5' or 'wwiii' to load
                previously fetched data, or array ordered by [val, lat, lon]
            load_wind:
                source of wind speed data. can be 'era5' or 'wwiii' to load
                previously fetched data, or array ordered by [val, lat, lon]
            north, south:
                latitude boundaries (float)
            west, east:
                longitude boundaries (float)
            top, bottom:
                depth range in metres (float)
                only applies to salinity and temperature
            start, end:
                time range for data load query (datetime)
                if multiple times exist within range, they will be averaged
                before computing interpolation
    """

    def __init__(self, 
            load_bathymetry=0, load_temp=0, load_salinity=0, load_wavedir=0, 
            load_waveheight=0, load_waveperiod=0, load_windspeed=0, 
            fetch=False, **kwargs):

        data = {}
        callbacks = []
        vartypes = ['bathy', 'temp', 'salinity', 
                'wavedir', 'waveheight', 'waveperiod', 'windspeed']
        load_args = [load_bathymetry, load_temp, load_salinity, 
                load_wavedir, load_waveheight, load_waveperiod, load_windspeed]

        # if load_args are not callable, convert it to a callable function
        for v, load_arg, ix in zip(vartypes, load_args, range(len(vartypes))):
            if callable(load_arg): continue

            elif isinstance(load_arg, str):
                key = f'{v}_{load_arg.lower()}'
                if fetch == True: fetch_map[key](**kwargs)
                callbacks.append(load_map[key])

            elif isinstance(load_arg, (int, float)):
                data[f'{v}_val'] = load_arg
                data[f'{v}_lat'] = kwargs['south'] 
                data[f'{v}_lon'] = kwargs['west']
                data[f'{v}_time'] = dt_2_epoch(kwargs['start'])[0] 
                if v in ('temp', 'salinity'): data[f'{v}_depth'] = kwargs['top']
                callbacks.append(load_callback)

            elif isinstance(load_arg, (list, tuple, np.ndarray)):
                if len(load_arg) not in (3, 4):
                    raise ValueError(f'invalid array shape for load_{v}. '
                    'arrays must be ordered by [val, lat, lon] for 2D data, or '
                    '[val, lat, lon, depth] for 3D data')
                data[f'{v}_val'] = load_arg[0]
                data[f'{v}_lat'] = load_arg[1]
                data[f'{v}_lon'] = load_arg[2]
                if len(load_arg) == 4: data[f'{v}_depth'] = load_arg[3]
                callbacks.append(load_callback)

            else: raise TypeError(f'invalid type for load_{v}. '
                  'valid types include string, float, array, and callable')

        q = Queue()

        pipe = zip(vartypes, callbacks)
        is_3D = [v in ('temp', 'salinity') for v in vartypes]
        is_arr = [not isinstance(arg, (int, float)) for arg in load_args]
        columns = [f(data=data, v=v, **kwargs) for v, f in pipe]
        intrpmap = [(Uniform2D, Uniform3D), (Interpolator2D, Interpolator3D)]
        reshapers = [reshape_3D if v else reshape_2D for v in is_3D]

        self.interps = {}
        interpolators = map(lambda x, y: intrpmap[x][y], is_arr, is_3D)
        interpolations = map(
            lambda i,r,c,v: Process(target=worker, args=(i,r,c,v,q)),
            interpolators, reshapers, columns, vartypes
        )

        for i in interpolations: i.start()
        while len(self.interps.keys()) < len(vartypes):
            obj = q.get()
            self.interps[obj[0]] = obj[1]
        for i in interpolations: i.join()
        q.close()
        return

    def bathy(self, lat, lon, grid=False):
        return self.interps['bathy'].interp(lat, lon, grid)

    def bathy_xy(self, x, y, grid=False):
        return self.interps['bathy'].interp_xy(x, y, z, grid)

    def bathy_deriv(self, lat, lon, axis='lon', grid=False):
        assert axis in ('lat', 'lon'), 'axis must be \'lat\' or \'lon\''
        return self.interps['bathy'].interp(lat, lon, grid,
              lat_deriv_order=(axis=='lat'), lon_deriv_order=(axis=='lon'))

    def bathy_deriv_xy(self, x, y, grid=False):
        assert axis in ('x', 'y'), 'axis must be \'x\' or \'y\''
        return self.interps['bathy'].interp_xy(x, y, grid,
                lat_deriv_order=(axis=='y'), lon_deriv_order=(axis=='x'))

    def temp(self, lat, lon, depth, grid=False):
        return self.interps['temp'].interp(lat, lon, depth, grid)

    def temp_xy(self, x, y, z, grid=False):
        return self.interps['temp'].interp_xy(x, y, z, grid)

    def salinity(self,lat, lon, depth, grid=False):
        return self.interps['salinity'].interp(lat, lon, depth, grid)

    def salinity_xy(self, x, y, z, grid=False):
        return self.interps['salinity'].interp_xy(x, y, z, grid)

    def wavedir(self, lat, lon, grid=False):
        return self.interps['wavedir'].interp(lat, lon, grid)

    def wavedir_xy(self, x, y, grid=False):
        return self.interps['wavedir'].interp_xy(x, y, grid)

    def waveheight(self, lat, lon, grid=False):
        return self.interps['waveheight'].interp(lat, lon, grid)

    def waveheight_xy(self, x, y, grid=False):
        return self.interps['waveheight'].interp_xy(x, y, grid)

    def waveperiod(self, lat, lon, grid=False):
        return self.interps['waveperiod'].interp(lat, lon, grid)

    def waveperiod_xy(self, x, y, grid=False):
        return self.interps['waveperiod'].interp_xy(x, y, grid)

    def windspeed(self, lat, lon, grid=False):
        return self.interps['windspeed'].interp(lat, lon, grid)

    def windspeed_xy(self, x, y, grid=False):
        return self.interps['windspeed'].interp_xy(x, y, grid)

