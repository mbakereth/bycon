#!/usr/local/bin/python3

import cgi, cgitb
import json, yaml
from os import path as path
from os import environ
import sys, os, datetime, argparse

# local
dir_path = path.dirname(path.abspath(__file__))
sys.path.append(path.join(path.abspath(dir_path), '..'))
from bycon.lib import *

"""podmd
* <https://progenetix.org/cgi/bycon/bin/biosamples.py?datasetIds=progenetix&assemblyId=GRCh38&includeDatasetResponses=ALL&referenceName=17&variantType=DEL&filterLogic=AND&start=4999999&start=7676592&end=7669607&end=10000000&filters=cellosaurus>
podmd"""

################################################################################
################################################################################
################################################################################

def main():

    biosamples("biosamples")
    
################################################################################

def biosamples(service):

    config = read_bycon_config( path.abspath( dir_path ) )
    these_prefs = read_local_prefs( service, dir_path )

    byc = {
        "config": config,
        "form_data": cgi_parse_query(),
        "errors": [ ],
        "warnings": [ ],
    }

    for d in [
        "dataset_definitions",
        "filter_definitions",
        "geoloc_definitions",
        "variant_definitions",
        "handover_definitions"
    ]:
        byc.update( { d: read_named_prefs( d, dir_path ) } )

    # first pre-population w/ defaults
    for d_k, d_v in these_prefs["defaults"].items():
        byc.update( { d_k: d_v } )

    # ... then modification if parameter in request
    if "method" in byc["form_data"]:
        m = byc["form_data"].getvalue("method")
        if m in these_prefs["methods"].keys():
            byc["method"] = m

    byc.update( { "dataset_ids": select_dataset_ids( **byc ) } )
    byc.update( { "dataset_ids": beacon_check_dataset_ids( **byc ) } )
    byc.update( { "filter_flags": get_filter_flags( **byc ) } )
    byc.update( { "filters": parse_filters( **byc ) } )

    # adding arguments for querying / processing data
    byc.update( { "variant_pars": parse_variants( **byc ) } )
    byc.update( { "variant_request_type": get_variant_request_type( **byc ) } )
    byc.update( { "queries": generate_queries( **byc ) } )

    # response prototype
    r = config["response_object_schema"]
    r.update( { "errors": byc["errors"], "warnings": byc["warnings"] } )

    # TODO: move somewhere
    if not byc[ "queries" ].keys():
      r["errors"].append( "No (correct) query parameters were provided." )
    if len(byc[ "dataset_ids" ]) < 1:
      r["errors"].append( "No `datasetIds` parameter provided." )
    if len(byc[ "dataset_ids" ]) > 1:
      r["errors"].append( "More than 1 `datasetIds` value was provided." )
    if len(r["errors"]) > 0:
      cgi_print_json_response( byc["form_data"], r, 422 )

    ds_id = byc[ "dataset_ids" ][ 0 ]

    # saving the parameters to the response
    for p in ["method", "filters", "variant_pars"]:
        r["parameters"].update( { p: byc[ p ] } )
    r["parameters"].update( { "dataset": ds_id } )
    r["response_type"] = service

    if "phenopackets" in byc["method"]:
        byc.update( { "response_type": "return_individuals" } )

    byc.update( { "query_results": execute_bycon_queries( ds_id, **byc ) } )
    query_results_save_handovers( **byc )

    access_id = byc["query_results"]["bs._id"][ "id" ]

    h_o, e = retrieve_handover( access_id, **byc )
    h_o_d, e = handover_return_data( h_o, e )
    if e:
        r["errors"].append( e )

    if len(r["errors"]) > 0:
      cgi_print_json_response( byc["form_data"], r, 422 )

    for b_s in h_o_d:
        s = { }
        for k in these_prefs["methods"][ byc["method"] ]:
            # TODO: harmless hack
            if k in b_s.keys():
                s[ k ] = b_s[ k ]
            else:
                s[ k ] = None
        r["data"].append( s )

    r[service+"_count"] = len(r["data"])
    cgi_print_json_response( byc["form_data"], r, 200 )

################################################################################
################################################################################

if __name__ == '__main__':
    main()
