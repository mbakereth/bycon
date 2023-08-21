# __init__.py
import sys
from os import environ, path
from pathlib import Path
import traceback

pkg_path = path.dirname( path.abspath(__file__) )
bycon_lib_path = path.join( pkg_path, "lib" )
sys.path.append( bycon_lib_path )

try:

    from aggregator_utils import *
    from args_parsing import *
    from bycon_helpers import *
    from bycon_plot import *
    from cgi_parsing import *
    from clustering_utils import *
    from data_retrieval import *
    from dataset_parsing import *
    from datatable_utils import *
    from handover_generation import *
    from interval_utils import *
    from file_utils import *
    from filter_parsing import *
    from query_execution import *
    from query_generation import *
    from read_specs import *
    from response_remapping import *
    from schema_parsing import *
    from service_utils import *
    from export_file_generation import *
    from variant_mapping import *
    from variant_parsing import *

    c_f = Path( path.join( pkg_path, "config.yaml" ) )
    config: object = load_yaml_empty_fallback( c_f )
    conf_dir = path.join( pkg_path, "config")
    byc: object = initialize_bycon(config)
    read_service_definition_files(conf_dir, byc)
    b_d = byc.get("beacon_defaults", {})
    defaults: object = b_d.get("defaults", {})
    for d_k, d_v in defaults.items():
        byc.update( { d_k: d_v } )

    cgi_parse_query(byc)
    
except Exception:

    if environ.get('HTTP_HOST'):
        print('Content-Type: text/plain')
        print('status: 302')
        print()
    
    print(traceback.format_exc())
    print()
    exit()
