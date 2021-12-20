import re, yaml, json
from pymongo import MongoClient
from os import path, pardir
from pathlib import Path
from json_ref_dict import RefDict, materialize
import humps

################################################################################

def read_bycon_configs_by_name(name, byc):

    """podmd
    Reading the config from the same wrapper dir:
    module
      |
      |- lib - read_specs.py
      |- config - __name__.yaml
    podmd"""

    o = {}
    ofp = path.join( byc["pkg_path"], "config", name+".yaml" )

    with open( ofp ) as od:
        o = yaml.load( od , Loader=yaml.FullLoader)

    byc.update({ name: o })

    return byc

################################################################################

def read_local_prefs(service, dir_path, byc):

    these_pars = ["config", "endpoints", "request_parameters"]

    for t_p in these_pars:
        t_k = "this_"+t_p
        byc.update({t_k: {}})

    d = Path( path.join( dir_path, "config", service ) )

    # old style named config
    f = Path( path.join( dir_path, "config", service+".yaml" ) )

    if f.is_file():
        byc.update({"this_config": load_yaml_empty_fallback( f ) })
        return byc

    elif d.is_dir():
        for t_p in these_pars:
            t_k = "this_"+t_p
            t_f_n = "{}.yaml".format(humps.camelize(t_p))
            t_f_p = Path( path.join( d, t_f_n ) )
            if t_f_p.is_file():
                byc.update({ t_k: load_yaml_empty_fallback(t_f_p) } )

    return byc   

################################################################################

def read_yaml_with_key_to_object(file_key, data_key, **paths):

    o = load_yaml_empty_fallback( path.join( paths[ "module_root" ], *paths[ file_key ] ) )

    if data_key in o:
        return o[ data_key ]

    # TODO: error capture & procedure
    return o

################################################################################

def dbstats_return_latest(byc):

    limit = 1
    if "stats_number" in byc:
        if byc["stats_number"] > 1:
            limit = byc["stats_number"]

    db = byc[ "config" ][ "info_db" ]
    coll = byc[ "config" ][ "beacon_info_coll" ]

    stats = MongoClient( )[ db ][ coll ].find( { }, { "_id": 0 } ).sort( "date", -1 ).limit( limit )
    return stats

################################################################################

def datasets_update_latest_stats(byc, collection_type="datasets"):

    results = [ ]

    def_k = re.sub(r's$', "_definitions", collection_type)
    q_k = re.sub(r's$', "_ids", collection_type)

    stat = dbstats_return_latest(byc)[0]

    for coll_id, coll in byc[ def_k ].items():
        if q_k in byc:
            if len(byc[ q_k ]) > 0:
                if not coll_id in byc[ q_k ]:
                    continue

        if collection_type in stat:
            if coll_id in stat[ collection_type ].keys():
                ds_vs = stat[ collection_type ][coll_id]
                if "counts" in ds_vs:
                    for c, c_d in byc["config"]["beacon_counts"].items():
                        if c_d["info_key"] in ds_vs["counts"]:
                            coll["info"].update({ c: ds_vs["counts"][ c_d["info_key"] ] })
                if "filtering_terms" in byc["response_type"]:
                    coll.update({ "filtering_terms": stat[ collection_type ][coll_id]["filtering_terms"] } )

        results.append(coll)

    return results

################################################################################

def update_datasets_from_dbstats(byc):

    ds_with_counts = datasets_update_latest_stats(byc)

    if not "beacon_info" in byc:
        byc["beacon_info"] = { }
    byc["beacon_info"].update( { "datasets": ds_with_counts } )

    if "service_info" in byc:
        for par in byc[ "beacon_info" ]:
            byc[ "service_info" ].update( { par: byc[ "beacon_info" ][ par ] } )

    return byc

################################################################################

def load_yaml_empty_fallback(yp):

    y = { }

    try:
        with open( yp ) as yd:
            y = yaml.load( yd , Loader=yaml.FullLoader)
    except:
        pass

    return y
