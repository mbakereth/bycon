import re, yaml
import json
from pymongo import MongoClient
from os import path as path
from os import environ

from .cgi_utils import *
################################################################################

def read_service_info(**paths):

    ofp = path.join( paths[ "module_root" ], *paths[ "service_info_file" ] )
    with open(ofp) as of:
        i = yaml.load( of , Loader=yaml.FullLoader)
        return(i["service_info"])

################################################################################

def read_beacon_info(**paths):

    ofp = path.join( paths[ "module_root" ], *paths[ "beacon_info_file" ] )
    with open(ofp) as of:
        i = yaml.load( of , Loader=yaml.FullLoader)
        return(i["beacon_info"])

################################################################################

def read_beacon_api_paths(**paths):

    pfp = path.join( paths[ "module_root" ], *paths[ "beacon_paths_file" ] )
    with open(pfp) as pf:
        p = yaml.load( pf , Loader=yaml.FullLoader)
        return(p["paths"])

################################################################################

def read_datasets_info(**paths):

    ofp = path.join( paths[ "module_root" ], *paths[ "beacon_datasets_file" ] )
    with open(ofp) as of:
        ds = yaml.load( of , Loader=yaml.FullLoader)
        return(ds["datasets"])

################################################################################

def read_handover_info(**paths):

    hfp = path.join( paths[ "module_root" ], *paths[ "handover_types_file" ] )
    with open(hfp) as of:
        ho = yaml.load( of , Loader=yaml.FullLoader)
        return(ho)

################################################################################

def dbstats_return_latest(**byc):

    dbstats_coll = MongoClient( )[ byc[ "config" ][ "info_db" ] ][ byc[ "config" ][ "beacon_info_coll" ] ]
    stats = dbstats_coll.find( { }, { "_id": 0 } ).sort( "date", -1 ).limit( 1 )
    return(stats[0])

################################################################################

def update_datasets_from_dbstats(**byc):

    ds_with_counts = [ ]
    for ds_id in byc["datasets_info"].keys():
        ds = byc["datasets_info"][ds_id]
        if ds_id in byc["dbstats"]["datasets"]:
            ds_db = byc["dbstats"]["datasets"][ ds_id ]
            for k, l in byc["config"]["beacon_info_count_labels"].items():
                if "counts" in ds_db:
                    if k in ds_db["counts"]:
                        ds[ l ] = ds_db["counts"][ k ]
        ds_with_counts.append(ds)

    return(ds_with_counts)