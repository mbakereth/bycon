#!/usr/local/bin/python3

import cgi, cgitb
import json, yaml
from os import path as path
from os import environ
import sys, os, datetime, argparse

# local
dir_path = path.dirname(path.abspath(__file__))
sys.path.append(path.join(path.abspath(dir_path), '..'))
from bycon import *

"""podmd

podmd"""

################################################################################
################################################################################
################################################################################

def main():

    biosamples("biosamples")
    
################################################################################

def biosamples(service):

    config = read_bycon_config( path.abspath( dir_path ) )
    these_prefs = read_service_prefs( service, dir_path )

    byc = {
        "config": config,
        "form_data": cgi_parse_query(),
        "filter_defs": read_filter_definitions( **config[ "paths" ] ),
        "variant_defs": read_yaml_to_object( "variant_definitions_file", **config[ "paths" ] ),
        "h->o": read_yaml_to_object( "handover_types_file", **config[ "paths" ] ),
        "datasets_info": read_yaml_with_key_to_object( "beacon_datasets_file", "datasets", **config[ "paths" ] )
    }

    # first pre-population w/ defaults
    for d_k, d_v in these_prefs["defaults"].items():
        byc.update( { d_k: d_v } )

    byc.update( { "dataset_ids": select_dataset_ids( **byc ) } )
    byc.update( { "dataset_ids": beacon_check_dataset_ids( **byc ) } )
    byc.update( { "filter_flags": get_filter_flags( **byc ) } )
    byc.update( { "filters": parse_filters( **byc ) } )

    # adding arguments for querying / processing data
    byc.update( { "variant_pars": parse_variants( **byc ) } )
    byc.update( { "variant_request_type": get_variant_request_type( **byc ) } )
    byc.update( { "queries": beacon_create_queries( **byc ) } )

    # response prototype
    r = config["response_object_schema"]

    # TODO: move somewhere
    if not byc[ "queries" ].keys():
      r["errors"].append( "No (correct) query parameters were provided." )
    if len(byc[ "dataset_ids" ]) < 1:
      r["errors"].append( "No `datasetIds` parameter provided." )
    if len(byc[ "dataset_ids" ]) > 1:
      r["errors"].append( "More than 1 `datasetIds` value was provided." )
    if len(r["errors"]) > 0:
      cgi_print_json_response( byc["form_data"], r )

    ds_id = byc[ "dataset_ids" ][ 0 ]

    # saving the parameters to the response
    for p in ["method", "filters", "variant_pars"]:
        r["parameters"].update( { p: byc[ p ] } )
    r["parameters"].update( { "dataset": ds_id } )
    r["data"][service] = [ ]

    byc.update( { "query_results": execute_bycon_queries( ds_id, **byc ) } )
    query_results_save_handovers( **byc )
    access_id = byc["query_results"]["bs._id"][ "id" ]
    bio_s = [ ]
    h_o, e = retrieve_handover( access_id, **byc )
    h_o_d, e = handover_return_data( h_o, e )
    if e:
        r["errors"].append( e )

    if len(r["errors"]) > 0:
      cgi_print_json_response( byc["form_data"], r )

    for b_s in h_o_d:
        s = { }
        for k in these_prefs["methods"][ byc["method"] ]:
            # TODO: harmless hack
            if k in b_s.keys():
                s[ k ] = b_s[ k ]
            else:
                s[ k ] = None
        r["data"][service].append( s )

    # TODO: testing only or general option?
    if "responseFormat" in byc["form_data"]:
        r_f = byc["form_data"].getvalue("responseFormat")
        if "simplelist" in r_f:
            r = r["data"][service]

    cgi_print_json_response( byc["form_data"], r )

################################################################################
################################################################################

if __name__ == '__main__':
    main()
