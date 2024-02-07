#!/usr/bin/env python3

from bycon import *

"""podmd

* <https://progenetix.org/beacon/service-info/>

podmd"""

################################################################################
################################################################################
################################################################################

def main():

    try:
        service_info()
    except Exception:
        print_text_response(traceback.format_exc(), byc["env"], 302)
    
################################################################################

def service_info():

    initialize_bycon_service(byc)

    defs = byc.get("beacon_defaults", {})
    b_e_d = defs.get("entity_defaults", {})
    pgx_info = b_e_d.get("info", {})
    c = pgx_info.get("content", {})
    info = object_instance_from_schema_name(byc, "ga4gh-service-info-1-0-0-schema", "")
    for k in info.keys():
        if k in c:
            info.update({k:c[k]})
    print_json_response(info, byc["env"])

################################################################################
################################################################################

if __name__ == '__main__':
    main()