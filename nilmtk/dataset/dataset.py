import os
import json
import copy
import pandas as pd
from nilmtk.building import Building
from nilmtk.sensors.electricity import MainsName
from nilmtk.sensors.electricity import ApplianceName
from nilmtk.sensors.electricity import Measurement
from nilmtk.sensors.electricity import DualSupply
from nilmtk.sensors.electricity import get_two_dataframes_of_dualsupply
from nilmtk.utils import summary_stats_string

"""Base class for all datasets."""


class DataSet(object):

    """Base class for all datasets.  This class can be used
    for loading nilmtk's REDD+ data format.

    Attributes
    ----------

    buildings : dict
        Each key is a string representing the name of the building and is
        preserved from the original dataset.  Each value is a
        nilmtk.building.Building object.

    metadata : dict
        Metadata regarding this DataSet.  Keys include:

        name : string
            Abbreviated name for the dataset, e.g. "REDD"

        full_name : string
            Full name of the dataset, eg. "Reference Energy Disaggregation Data Set"

        urls : list of strings, optional
            The URL(s) for more information about this dataset

        citations : list of strings, optional
            Academic citation(s) for this dataset

        nominal_voltage : float, optional

        timezone : string

        geographic_coordinates : pair (lat, long), optional
            The geo location of the research institution.  Used as a fall back
            if geo location isn't available for any individual building.

    """

    def __init__(self):
        self.buildings = {}
        self.metadata = {}

    def load(self, root_directory):
        """Load entire dataset into memory"""
        building_names = self.load_building_names(root_directory)
        for building in building_names:
            self.load_building(root_directory, building)

    def load_hdf5(self, directory):
        """Imports dataset from HDF5 store into NILMTK object

        Parameters
        ----------

        directory : str
            Directory where the HDF5 store is located

        """
        # Load metadata if exists
        if os.path.isfile(os.path.join(directory, 'metadata.json')):
            with open(os.path.join(directory, 'metadata.json'), 'r') as metadata_fp:
                self.metadata = json.loads(metadata_fp.read())
        store = pd.HDFStore(
            os.path.join(directory, 'dataset.h5'))
        self.buildings = {}

        # Finding all keys stored in the HDF5 store
        keys = store.keys()

        # Finding the buildings
        building_numbers = list(set([key.split("/")[1] for key in keys]))

        # Loading the structured information for each building
        for building_number in building_numbers:

            # Create a new building and add it to buildings
            b = Building()
            self.buildings[int(building_number)] = b

            # Find the keys which start with this particular building
            keys_building = [
                key for key in keys if key.split("/")[1] == building_number]

            # Loading utilites
            keys_utilities = [
                key for key in keys_building if "utility" in key]

            # Load electric if len(keys_utilities)>0

            if len(keys_utilities) > 0:
                # Load electric
                keys_electric = [
                    key for key in keys_utilities if "electric" in key]

                # Loading mains
                keys_mains = [
                    key for key in keys_electric if "mains" in key]

                if len(keys_mains) > 0:
                    b.utility.electric.mains = {}
                    for key in keys_mains:
                        mains_split = int(key.split("/")[-2])
                        mains_meter = int(key.split("/")[-1])
                        mains_name = MainsName(mains_split, mains_meter)
                        b.utility.electric.mains[mains_name] = store[key]

                # Loading appliances
                keys_appliances = [
                    key for key in keys_electric if "appliances" in key]

                if len(keys_appliances) > 0:
                    b.utility.electric.appliances = {}
                    for key in keys_appliances:
                        appliance_name = key.split("/")[-2]
                        appliance_instance = int(key.split("/")[-1])
                        appliance_name = ApplianceName(
                            appliance_name, appliance_instance)
                        b.utility.electric.appliances[
                            appliance_name] = store[key]

    def export_csv(self, directory):
        """Exports dataset in nilmtk standard on-disk CSV format.

        Parameters
        ----------
        directory : Complete path where to export the data
        """

        # Mapping from {Appliance/Mains/Circuit}Name to CSV name
        namedtuple_map = {'mains': lambda x: "%d_%d.csv" %
                          (x.split, x.meter),
                          'appliances': lambda x: "%s_%d.csv" %
                          (x.name, x.instance),
                          'circuits': lambda x: "%s_%d_%d.csv"
                          % (x.name, x.split, x.meter)
                          }
        # Mapping from {appliance/mains/circuit} to directory structure
        folder_path_map = {'mains': lambda x: "building_%d/utility/electric/mains/"
                           % (building_number),
                           'appliances': lambda x: "building_%d/utility/electric/appliances/"
                           % (building_number),
                           'circuits': lambda x: "building_%d/utility/electric/circuits/"
                           % (building_number)
                           }
        # Mapping from {Measurement/DualSupply} to CSV column header
        column_mapping = {'dual': lambda x: "%s_%s_%d" %
                          (x.measurement.physical_quantity,
                           x.measurement.type, x.supply),
                          'single': lambda x: "%s_%s" %
                          (x.physical_quantity, x.type)
                          }

        # Write metadata
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(os.path.join(directory, 'metadata.json'), 'w') as metadata_fp:
            metadata_fp.write(json.dumps(self.metadata))

        def create_path_df(building_number, df_name, df, df_type, column):
            """Creates corresponding path in the nilmtk folder hierarchy for df,
             if the path does not exist. Also, saves the dataset in epoch unix
             timestamped CSVs. CSV name correpsond to namedtuple_map

            Parameters
            ----------
            building_number : nilmtk.Building number, int
            df_name : nilmtk.sensor.electricity.{appliance/mains/circuits}Name
            df : pandas.DataFrame consisting of DatetimeIndex and nilmtk.sensors.
            utility.electric.Measurement as columns
            df_type : string, one of ['mains', 'appliances','circuits']
            column: string, one of ['dual', 'single']
            """

            dir_path = os.path.join(
                directory, folder_path_map[df_type](building_number))
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            temp = df.copy()
            temp.index = (df.index.astype(int) / 1e9).astype(int)
            temp.rename(columns=column_mapping[column], inplace=True)
            temp.to_csv(os.path.join(dir_path, namedtuple_map[df_type
                                                              ](df_name)),
                        float_format='%.2f',
                        index_label="timestamp")

        for building_number in self.buildings:
            print("Writing data for building %d" % (building_number))
            building = self.buildings[building_number]
            utility = building.utility
            electric = utility.electric
            mains = electric.mains
            appliances = electric.appliances
            circuits = electric.circuits
            for main_name, main_df in mains.iteritems():
                create_path_df(building_number, main_name,
                               main_df, 'mains', 'single')

            for appliance_name, appliance_df in appliances.iteritems():
                if isinstance(appliance_df.columns[0], DualSupply):
                    create_path_df(
                        building_number, appliance_name, appliance_df,
                        'appliances', 'dual')
                else:
                    create_path_df(
                        building_number, appliance_name, appliance_df,
                        'appliances', 'single')

            for circuit_name, circuit_df in circuits.iteritems():
                create_path_df(building_number, circuit_name, circuit_df,
                               'circuit', 'single')

    def export(self, directory, format='HDF5', compact=False):
        """Export dataset to disk as HDF5.

        Parameters
        ----------
        directory : str
            Output directory

        format : str, optional
            `REDD+` or `HDF5`

        compact : boolean, optional
            Defaults to false.  If True then only save change points.
        """
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(os.path.join(directory, 'metadata.json'), 'w') as metadata_fp:
            metadata_fp.write(json.dumps(self.metadata))

        # Store metadata

        store = pd.HDFStore(
            os.path.join(directory, 'dataset.h5'), complevel=9, complib='zlib')
        for building_number in self.buildings:
            print("Writing data for %d" % (building_number))
            building = self.buildings[building_number]
            utility = building.utility
            electric = utility.electric
            mains = electric.mains
            for main in mains:

                store.put('/%d/utility/electric/mains/%d/%d/' %
                          (building_number, main.split, main.meter),
                          mains[main], table=True)
            appliances = electric.appliances
            for appliance in appliances:
                store.put('%d/utility/electric/appliances/%s/%d/' %
                          (building_number, appliance.name,
                           appliance.instance),
                          appliances[appliance], table=True)
        store.close()

    def get_n_appliances_per_building(self):
        """
        Returns
        -------
        list : number of appliances per building (not necessarily in order)
        """
        return [len(building.utility.electric.appliances) 
                for building in self.buildings.values()]

    def __str__(self):
        s = ''
        s += 'name : ' + self.metadata.get('name', 'NOT DEFINED') + '\n'
        s += 'number of buildings : {:d}\n'.format(len(self.buildings))
        s += 'number of appliances per building :\n'
        s += summary_stats_string(self.get_n_appliances_per_building())
        return s
        

    # This will be overridden by each subclass
    def load_building_names(self, root_directory):
        """return list of building names"""
        raise NotImplementedError

    # This will be overridden by each subclass
    def load_building(self, root_directory, building_name):
        # convert units
        # convert to standard appliance names
        raise NotImplementedError

    def to_json_temp(self):
        return json.dumps(self, default=lambda o: o.__dict__,
                          sort_keys=True, indent=4)

    def to_json(self):
        '''Returns the JSON representation of the dataset'''
        representation = copy.copy(self.metadata)
        representation["buildings"] = {}
        # Accessing list of buildings
        for building_name, building in self.buildings.iteritems():
            representation["buildings"][building_name] = building.to_json()

        return json.dumps(representation)
